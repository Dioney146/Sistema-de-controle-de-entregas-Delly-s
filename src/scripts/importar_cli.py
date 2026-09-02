#!/usr/bin/env python3
"""Importa um export do Wynthor direto no banco (Postgres/Supabase),
sem passar pela interface do Streamlit.

Reaproveita exatamente a mesma lógica usada na página
`pages/3_importar_whyntor.py`: leitura em `src/importer.ler_arquivo`,
consolidação por NUMCAR em `src/importer.consolidar` e gravação em
`src/db.inserir_cargas_em_lote`. Por isso o comportamento (dedup por
NUMCAR, cálculo de prazo, etc.) fica idêntico ao do site.

USO
---
    export DATABASE_URL="postgresql://postgres.xxxx:SENHA@aws-0-sa-east-1.pooler.supabase.com:6543/postgres"
    python scripts/importar_cli.py caminho/arquivo.xls rodoviario

    # ano de referência diferente do atual (quando o DESTINO só traz dia/mês)
    python scripts/importar_cli.py caminho/arquivo.xls rodoviario --ano 2026

    # não cadastrar municípios novos automaticamente
    python scripts/importar_cli.py caminho/arquivo.xls rodoviario --sem-cadastro-municipio

Coloque este arquivo em `scripts/importar_cli.py` dentro do seu repositório
(mesmo nível que a pasta `src/`) para os imports funcionarem.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

# garante que "src" seja importável rodando o script de qualquer diretório
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db, importer  # noqa: E402
from src.config import MODALIDADES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa export do Wynthor direto no banco (Supabase/Postgres)."
    )
    parser.add_argument("arquivo", help="Caminho do .xls/.xlsx/.csv exportado do Wynthor")
    parser.add_argument(
        "modalidade", choices=list(MODALIDADES.keys()),
        help="Modalidade de entrega (mesma usada no site)",
    )
    parser.add_argument(
        "--ano", type=int, default=date.today().year,
        help="Ano de referência para destinos sem ano explícito (padrão: ano atual)",
    )
    parser.add_argument(
        "--sem-cadastro-municipio", action="store_true",
        help="Não cadastrar automaticamente municípios novos encontrados no arquivo",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        print("ERRO: defina a variável de ambiente DATABASE_URL antes de rodar este script.")
        print('Exemplo:')
        print('  export DATABASE_URL="postgresql://postgres.xxxx:SENHA@'
              'aws-0-sa-east-1.pooler.supabase.com:6543/postgres"')
        return 1

    caminho = Path(args.arquivo)
    if not caminho.exists():
        print(f"ERRO: arquivo não encontrado: {caminho}")
        return 1

    print(f"Lendo {caminho.name}...")
    bruto = importer.ler_arquivo(str(caminho))

    resumo = importer.resumo_arquivo(bruto)
    print(f"  Linhas (notas):  {resumo['linhas']}")
    print(f"  Carregamentos:   {resumo['carregamentos']}")
    print(f"  Peso total:      {resumo['peso_total_kg']:.3f} kg")
    print(f"  Valor total:     R$ {resumo['valor_total']:.2f}")
    print(f"  Período:         {resumo['periodo']}")

    print("\nConsultando prazos cadastrados e carregamentos já importados...")
    cadastro = db.listar_municipios(args.modalidade)
    prazos = dict(zip(cadastro["nome"], cadastro["prazo_dias"])) if not cadastro.empty else {}

    try:
        consolidado = importer.consolidar(bruto, args.modalidade, prazos, args.ano)
    except ValueError as erro:
        print(f"ERRO: {erro}")
        return 1

    if consolidado.empty:
        print("Nenhum carregamento encontrado no arquivo.")
        return 0

    existentes = db.numcars_existentes(args.modalidade)
    consolidado["ja_importado"] = consolidado["numcar"].isin(existentes)
    novos = consolidado[~consolidado["ja_importado"]]

    print(f"\n{len(consolidado)} carregamento(s) no arquivo, {len(novos)} novo(s) a importar.")
    if novos.empty:
        print("Todos os carregamentos já estavam no banco. Nada a fazer.")
        return 0

    registros = novos.drop(columns=["destino_original", "ja_importado"]).to_dict("records")
    resultado = db.inserir_cargas_em_lote(registros)

    if not args.sem_cadastro_municipio:
        for _, linha in novos.iterrows():
            db.sincronizar_municipio(args.modalidade, linha["municipio"], linha["uf"])

    print(f"\n✅ {resultado['inseridos']} carregamento(s) importado(s) com sucesso no Supabase.")
    if resultado["ignorados"]:
        print("⚠️  Ignorados (NUMCAR já existente, gravado por outra execução em paralelo): "
              + ", ".join(resultado["ignorados"]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
