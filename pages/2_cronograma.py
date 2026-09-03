"""Cronograma mensal — grade município × dia, no formato da planilha original."""

from __future__ import annotations

import calendar

import pandas as pd
import streamlit as st

from src import db, metrics, ui
from src.config import MESES, MODALIDADES, STATUS, STATUS_CORES

ui.configurar_pagina("Cronograma", "📅")

modalidade = ui.seletor_modalidade()
ano, mes = ui.seletor_periodo(modalidade)
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
dias_no_mes = calendar.monthrange(ano, mes)[1]
ui.cabecalho('<span class="marca">◤</span> CRONOGRAMA DE CORTES',
             f"{info['icone']} {info['label']}",
             f"01/{mes:02d}/{ano} — {dias_no_mes}/{mes:02d}/{ano}")

df_ano = db.listar_cargas(modalidade, ano=ano)
df_mes = df_ano[df_ano["mes"] == mes] if not df_ano.empty else df_ano

cadastro = db.listar_municipios(modalidade, somente_ativos=True)
municipios = cadastro["nome"].tolist() if not cadastro.empty else []
if not df_mes.empty:
    municipios += [m for m in df_mes["municipio"].unique() if m not in municipios]

indicadores = metrics.kpis(df_mes)
topo = st.columns(4)
topo[0].metric("Cargas no mês", indicadores["cargas"])
topo[1].metric("Entregues", indicadores["entregues"])
topo[2].metric("Peso (t)", f"{indicadores['peso_t']:.3f}")
topo[3].metric("Municípios ativos", len(municipios))

if not municipios:
    st.warning("Cadastre municípios desta modalidade na página **Cadastros** "
               "para montar a grade do cronograma.")
    st.stop()

matriz = metrics.matriz_cronograma(df_mes, municipios, ano, mes)


def _pintar(valor: str) -> str:
    texto = str(valor).strip()
    if not texto:
        return ""
    codigo = texto[0] if texto[0] in STATUS_CORES else None
    if texto.endswith("x"):
        return "background-color: #6C5B7B; color: white; font-weight: 600;"
    if codigo:
        return f"background-color: {STATUS_CORES[codigo]}; color: white; font-weight: 600;"
    return ""


colunas_dias = [c for c in matriz.columns if c != "Município"]
estilo = (matriz.style
          .map(_pintar, subset=colunas_dias)
          .set_properties(subset=colunas_dias, **{"text-align": "center"}))

ui.secao("Grade do mês", "cada célula traz o status da carga na data de corte")
st.dataframe(estilo, width="stretch", hide_index=True,
             height=min(80 + 35 * len(matriz), 600))

legenda = " · ".join(f"**{codigo}** {nome}" for codigo, nome in STATUS.items())
st.caption(f"Legenda: {legenda} · **2x** mais de uma carga no mesmo dia")

st.divider()
ui.secao("Totais por município")
totais = metrics.totais_por_municipio_mes(df_mes, municipios)
st.dataframe(totais, width="stretch", hide_index=True)

st.divider()
with st.expander("Exportar cronograma"):
    csv = matriz.to_csv(index=False, sep=";", encoding="utf-8-sig")
    st.download_button(
        "Baixar grade em CSV", csv,
        file_name=f"cronograma_{modalidade}_{ano}_{mes:02d}.csv",
        mime="text/csv",
    )
    if not df_mes.empty:
        st.download_button(
            "Baixar cargas do mês em CSV",
            df_mes.drop(columns=["peso_t", "identificacao"], errors="ignore").to_csv(index=False, sep=";"),
            file_name=f"cargas_{modalidade}_{ano}_{mes:02d}.csv",
            mime="text/csv",
        )
