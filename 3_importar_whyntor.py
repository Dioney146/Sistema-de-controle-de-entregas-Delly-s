"""Importação do export do Wynthor (.xls) para o banco de dados."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import db, importer, ui
from src.config import MODALIDADES

ui.configurar_pagina("Importar Wynthor", "📥")

modalidade = ui.seletor_modalidade()
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
ui.cabecalho(f"📥 Importar carregamentos — {info['label']}",
             "envie o arquivo exportado do Wynthor; as notas são agrupadas por NUMCAR")

st.markdown(
    "**Mapeamento aplicado:** `NUMCAR` → Carregamento · `TOTPESO` → Peso (somado "
    "por carregamento) · `DESTINO` → Destino (UF, município e data). Quando "
    "existirem, `DTSAIDA`, `VLTOTAL`, `NUMNOTA`, `CODCLI`, `PLACA` e `NMOTORA` "
    "também são aproveitados."
)

arquivo = st.file_uploader("Arquivo do Wynthor", type=["xls", "xlsx", "csv"])

if arquivo is None:
    st.stop()

try:
    bruto = importer.ler_arquivo(arquivo)
except Exception as erro:
    st.error(f"Não consegui ler o arquivo: {erro}")
    st.stop()

resumo = importer.resumo_arquivo(bruto)
colunas = st.columns(4)
colunas[0].metric("Linhas (notas)", resumo["linhas"])
colunas[1].metric("Carregamentos", resumo["carregamentos"])
colunas[2].metric("Peso total", f"{resumo['peso_total_kg']:,.3f} kg")
colunas[3].metric("Valor total", ui.formatar_reais(resumo["valor_total"]))
st.caption(f"Período do arquivo: {resumo['periodo']}")

with st.expander("Ver as primeiras linhas do arquivo bruto"):
    st.dataframe(bruto.head(20), width="stretch")

cadastro = db.listar_municipios(modalidade)
prazos = dict(zip(cadastro["nome"], cadastro["prazo_dias"])) if not cadastro.empty else {}

ano_ref = st.number_input("Ano de referência (usado quando o DESTINO só traz dia/mês)",
                          min_value=2020, max_value=2100, value=date.today().year)

try:
    consolidado = importer.consolidar(bruto, modalidade, prazos, int(ano_ref))
except ValueError as erro:
    st.error(str(erro))
    st.stop()

if consolidado.empty:
    st.warning("Nenhum carregamento encontrado no arquivo.")
    st.stop()

st.divider()
st.subheader(f"{len(consolidado)} carregamento(s) prontos para importar")

existentes = db.numcars_existentes(modalidade)
consolidado["já_importado"] = consolidado["numcar"].isin(existentes)

previa = consolidado[["numcar", "destino_original", "data_saida", "municipio", "uf",
                      "pedidos", "clientes", "peso_kg", "valor", "previsao_entrega",
                      "veiculo", "já_importado"]].rename(columns={
    "numcar": "Carregamento", "destino_original": "Destino",
    "data_saida": "Saída", "municipio": "Município", "uf": "UF",
    "pedidos": "Notas", "clientes": "Clientes", "peso_kg": "Peso (kg)",
    "valor": "Valor (R$)", "previsao_entrega": "Previsão",
    "veiculo": "Veículo/Placa", "já_importado": "Já importado",
})
st.dataframe(previa, width="stretch", hide_index=True)

novos = consolidado[~consolidado["já_importado"]]
if novos.empty:
    st.info("Todos os carregamentos deste arquivo já estão no banco.")
    st.stop()

criar_municipios = st.checkbox(
    "Cadastrar automaticamente municípios que ainda não existem nesta modalidade",
    value=True,
)

if st.button(f"⬆️ Importar {len(novos)} carregamento(s)", type="primary"):
    registros = novos.drop(columns=["destino_original", "já_importado"]).to_dict("records")
    resultado = db.inserir_cargas_em_lote(registros)
    if criar_municipios:
        for _, linha in novos.iterrows():
            db.sincronizar_municipio(modalidade, linha["municipio"], linha["uf"])
    st.success(f"{resultado['inseridos']} carregamento(s) importado(s) com sucesso.")
    if resultado["ignorados"]:
        st.warning("Ignorados (NUMCAR já existente): "
                   + ", ".join(resultado["ignorados"]))
    st.balloons()
