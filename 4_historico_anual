"""Histórico anual — mapa município × mês e resumo da operação."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from src import db, metrics, ui
from src.config import MESES_CURTOS, MODALIDADES

ui.configurar_pagina("Histórico anual", "📈")

modalidade = ui.seletor_modalidade()
ano, _ = ui.seletor_periodo(modalidade, com_mes=False)
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
ui.cabecalho(f"{info['icone']} Histórico anual — {info['label']}",
             f"matriz município × mês do ano {ano}")

df_ano = db.listar_cargas(modalidade, ano=ano)
cadastro = db.listar_municipios(modalidade, somente_ativos=True)
municipios = cadastro["nome"].tolist() if not cadastro.empty else []
if not df_ano.empty:
    municipios += [m for m in df_ano["municipio"].unique() if m not in municipios]

indicador = st.selectbox("Indicador", list(metrics.INDICADORES_ANUAIS.keys()))
matriz = metrics.mapa_anual(df_ano, municipios, indicador)

if matriz.empty:
    st.info("Sem dados para o ano selecionado.")
    st.stop()

st.dataframe(
    matriz.style.background_gradient(cmap="Oranges", subset=MESES_CURTOS)
          .format(precision=2, subset=MESES_CURTOS + ["Total ano"]),
    width="stretch", hide_index=True,
)

st.divider()
col_a, col_b = st.columns(2)

with col_a:
    st.markdown(f"**{indicador} por mês**")
    totais_mes = matriz[MESES_CURTOS].sum() if indicador != "% no prazo" \
        else matriz[MESES_CURTOS].replace(0, None).mean()
    fig = px.bar(x=MESES_CURTOS, y=totais_mes.values, height=320,
                 labels={"x": "", "y": indicador},
                 color_discrete_sequence=["#4C78A8"])
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")

with col_b:
    st.markdown(f"**{indicador} por município (ano)**")
    ranking = matriz[["Município", "Total ano"]].sort_values("Total ano", ascending=True)
    fig2 = px.bar(ranking, x="Total ano", y="Município", orientation="h",
                  height=320, color_discrete_sequence=["#E4572E"])
    fig2.update_layout(margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig2, width="stretch")

st.divider()
st.markdown("**Resumo mensal da operação**")
resumo = metrics.resumo_mensal_operacao(df_ano)
st.dataframe(resumo, width="stretch", hide_index=True)

st.download_button(
    "Baixar histórico anual (CSV)",
    matriz.to_csv(index=False, sep=";", encoding="utf-8-sig"),
    file_name=f"historico_{modalidade}_{ano}_{indicador}.csv",
    mime="text/csv",
)
