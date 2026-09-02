"""Importação do export do Wynthor — nível de nota fiscal, com data de corte manual."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src import db, importer, ui
from src.config import MODALIDADES, PRAZO_PADRAO_DIAS

ui.configurar_pagina("Importar Wynthor", "📥")

modalidade = ui.seletor_modalidade()
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
label_placa = info["doc_label"]

ui.cabecalho(f"📥 Importar do Wynthor — {info['label']}",
             "as notas entram individualmente para o checkout por cliente")

st.markdown(
    "**Colunas usadas:** `CODCLI`, `CLIENTE`, `NUMNOTA` e `NUMCAR`. "
    f"`DESTINO` e `PLACA` servem só para montar a carga — que é identificada por "
    f"**data de corte + município + {label_placa.lower()}**. Uma mesma "
    f"{label_placa.lower()} pode levar mais de um carregamento na mesma viagem: "
    "nesse caso os dois caem na mesma carga."
)

arquivo = st.file_uploader("Arquivo do Wynthor", type=["xls", "xlsx", "csv"])
if arquivo is None:
    st.stop()

try:
    bruto = importer.ler_arquivo(arquivo)
    notas = importer.preparar_notas(bruto)
except Exception as erro:
    st.error(f"Não consegui ler o arquivo: {erro}")
    st.stop()

resumo = importer.resumo_arquivo(bruto)
colunas = st.columns(4)
colunas[0].metric("Linhas", resumo["linhas"])
colunas[1].metric("Notas fiscais", resumo["notas"])
colunas[2].metric("Clientes", resumo["clientes"])
colunas[3].metric("Carregamentos", resumo["carregamentos"])
st.caption(f"Data de saída que veio no Wynthor: {resumo['saida_wynthor']} "
           "— informativa apenas, o corte é o que você escolher abaixo.")

st.divider()

# ---------------------------------------------------------------------------
# 1. Data de corte (manual)
# ---------------------------------------------------------------------------
st.subheader("1. Data de corte")

abertas = db.listar_programacoes_abertas(modalidade)
data_sugerida = date.today()

if not abertas.empty:
    st.markdown("**Cortes programados aguardando arquivo:**")
    resumo_abertas = abertas[["data_corte", "municipio", "placa"]].rename(
        columns={"data_corte": "Corte", "municipio": "Município", "placa": label_placa})
    st.dataframe(resumo_abertas, width="stretch", hide_index=True,
                 column_config={"Corte": st.column_config.DateColumn(format="DD/MM/YYYY")})

    opcoes = sorted(abertas["data_corte"].dropna().dt.date.unique(), reverse=True)
    usar_programado = st.checkbox("Usar uma data de corte já programada", value=True)
    if usar_programado:
        data_sugerida = st.selectbox(
            "Corte programado", opcoes, format_func=lambda d: d.strftime("%d/%m/%Y"))
else:
    st.caption("Nenhum corte programado em aberto. Você pode programar os cortes "
               "na página **Programar cortes** assim que eles acontecerem, sem "
               "esperar o faturamento.")

col_data, col_prazo = st.columns(2)
data_corte = col_data.date_input(
    "Data de corte desta carga", value=data_sugerida, format="DD/MM/YYYY",
    help="É o corte real da operação, não o DTSAIDA do Wynthor.",
)
dias_prazo = col_prazo.number_input("Prazo de entrega (dias após o corte)",
                                    min_value=0, value=PRAZO_PADRAO_DIAS)

# ---------------------------------------------------------------------------
# 2. Conferência das cargas
# ---------------------------------------------------------------------------
st.subheader("2. Confira as cargas")
grupos = importer.resumir_grupos(notas)
st.caption("Corrija o município ou a placa se vieram errados do arquivo. "
           "Cada linha vira uma carga.")

grupos_editados = st.data_editor(
    grupos.drop(columns=["grupo"]),
    width="stretch", hide_index=True, num_rows="fixed",
    disabled=["Carregamentos", "Notas", "Clientes", "Peso (kg)",
              "Valor (R$)", "Saída no Wynthor"],
    key="editor_grupos",
)

# remapeia o que o usuário eventualmente corrigiu na tabela
mapa = {}
for posicao, chave in enumerate(grupos["grupo"]):
    linha = grupos_editados.iloc[posicao]
    mapa[chave] = {
        "municipio": str(linha["Município"]).strip(),
        "uf": str(linha["UF"]).strip().upper()[:2] or "AM",
        "placa": str(linha["Placa"]).strip().upper(),
    }

sem_municipio = [c for c, v in mapa.items() if not v["municipio"]]
if sem_municipio:
    st.error("Preencha o município de todas as linhas antes de importar.")
    st.stop()

# ---------------------------------------------------------------------------
# 3. Prévia das notas
# ---------------------------------------------------------------------------
with st.expander(f"Ver as {len(notas)} notas que serão importadas"):
    previa = notas[["numcar", "numnota", "codcli", "cliente", "municipio", "placa"]]
    st.dataframe(previa.rename(columns={
        "numcar": "Carregamento", "numnota": "Nota fiscal", "codcli": "Cód. cliente",
        "cliente": "Cliente", "municipio": "Município", "placa": label_placa,
    }), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# 4. Importar
# ---------------------------------------------------------------------------
st.subheader("3. Importar")
criar_cadastros = st.checkbox(
    "Cadastrar automaticamente municípios e placas que ainda não existem", value=True)

if st.button(f"⬆️ Importar {len(notas)} nota(s) em {len(mapa)} carga(s)",
             type="primary"):
    total_notas, total_repetidas, criadas, atualizadas = 0, 0, 0, 0

    for chave, dados_grupo in mapa.items():
        recorte = notas[notas["grupo"] == chave]
        motorista = next((m for m in recorte["motorista"].dropna().unique() if m), None)
        peso = float(recorte["peso_kg"].sum())
        valor = float(recorte["valor"].sum())
        saidas = recorte["data_saida_origem"].dropna()

        carga_id, foi_criada = db.obter_ou_criar_carga(
            modalidade, data_corte, dados_grupo["municipio"], dados_grupo["placa"],
            extras={
                "uf": dados_grupo["uf"],
                "motorista": motorista,
                "previsao_entrega": data_corte + timedelta(days=int(dias_prazo)),
                "data_saida_origem": saidas.min().date() if not saidas.empty else None,
                "peso_kg": peso,
                "valor": valor,
                "origem_dado": "wynthor",
            },
        )
        criadas += int(foi_criada)
        atualizadas += int(not foi_criada)

        resultado = db.inserir_notas(carga_id, modalidade, recorte.to_dict("records"))
        total_notas += resultado["inseridas"]
        total_repetidas += resultado["repetidas"]

        if not foi_criada:  # soma o peso/valor do novo carregamento na carga existente
            atual = db.buscar_carga_por_id(carga_id) or {}
            db.salvar_carga({
                "peso_kg": float(atual.get("peso_kg") or 0) + peso,
                "valor": float(atual.get("valor") or 0) + valor,
            }, carga_id=carga_id)

        if criar_cadastros:
            db.sincronizar_municipio(modalidade, dados_grupo["municipio"], dados_grupo["uf"])
            db.sincronizar_veiculo(modalidade, dados_grupo["placa"], motorista)

    st.success(f"{total_notas} nota(s) importada(s) · {criadas} carga(s) nova(s) "
               f"· {atualizadas} carga(s) já programada(s)/existente(s) "
               "recebeu(ram) as notas.")
    if total_repetidas:
        st.info(f"{total_repetidas} nota(s) já estavam no banco e foram ignoradas.")
    st.caption("Agora é só ir na página **Checkout** para dar baixa por cliente.")
