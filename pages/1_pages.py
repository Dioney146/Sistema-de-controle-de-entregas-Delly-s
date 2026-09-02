"""Painel de indicadores — visão do mês e do ano."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from src import db, metrics, ui
from src.config import MESES, MODALIDADES, STATUS, STATUS_CORES

ui.configurar_pagina("Painel", "📊")

modalidade = ui.seletor_modalidade()
ano, mes = ui.seletor_periodo(modalidade)
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
ui.cabecalho(
    f"{info['icone']} Painel de Controle — {info['label']}",
    f"{MESES[mes - 1]} / {ano} · acompanhamento mensal e acumulado do ano",
)

df_ano = db.listar_cargas(modalidade, ano=ano)
df_mes = df_ano[df_ano["mes"] == mes] if not df_ano.empty else df_ano

kpi_mes = metrics.kpis(df_mes)
kpi_ano = metrics.kpis(df_ano)

if kpi_ano["cargas"] == 0:
    st.info(
        "Ainda não há cargas registradas nesta modalidade. Use **Importar Wynthor** "
        "para carregar o arquivo do carregamento ou **Entregas** para lançar manualmente."
    )

# --------------------------------------------------------------------------
# KPIs do mês
# --------------------------------------------------------------------------
st.subheader(f"Mês — {MESES[mes - 1]}/{ano}")
linha1 = st.columns(4)
linha1[0].metric("Cargas programadas", ui.formatar_numero(kpi_mes["cargas"]),
                 help="viagens planejadas no mês (exclui canceladas)")
linha1[1].metric("Entregues", ui.formatar_numero(kpi_mes["entregues"]),
                 help="cargas concluídas")
linha1[2].metric("% conclusão", f"{kpi_mes['conclusao']:.1f}%",
                 help="entregues / programadas")
linha1[3].metric("% no prazo (OTIF)", f"{kpi_mes['otif']:.1f}%",
                 help="entregas dentro da previsão")

linha2 = st.columns(4)
linha2[0].metric("Notas fiscais", ui.formatar_numero(kpi_mes["notas"]),
                 help="notas importadas no mês")
linha2[1].metric("Checkout", f"{kpi_mes['checkout']:.1f}%",
                 help="notas já conferidas (entregues, devolvidas ou reagendadas)")
linha2[2].metric("Notas pendentes", ui.formatar_numero(kpi_mes["notas_pendentes"]))
linha2[3].metric("Notas com ocorrência", ui.formatar_numero(kpi_mes["notas_ocorrencia"]))

linha3 = st.columns(4)
linha3[0].metric("Peso expedido", f"{kpi_mes['peso_t']:.3f} t")
linha3[1].metric("Valor expedido", ui.formatar_reais(kpi_mes["valor"]))
linha3[2].metric("Fora do prazo", ui.formatar_numero(kpi_mes["fora_prazo"]))
linha3[3].metric("Municípios no mês", ui.formatar_numero(kpi_mes["municipios"]))

st.divider()

# --------------------------------------------------------------------------
# Acumulado do ano
# --------------------------------------------------------------------------
st.subheader(f"Acumulado do ano — {ano}")
linha4 = st.columns(4)
linha4[0].metric("Cargas no ano", ui.formatar_numero(kpi_ano["cargas"]))
linha4[1].metric("Entregues no ano", ui.formatar_numero(kpi_ano["entregues"]))
linha4[2].metric("% no prazo (ano)", f"{kpi_ano['otif']:.1f}%")
linha4[3].metric("Municípios atendidos", ui.formatar_numero(kpi_ano["municipios"]))

st.divider()

# --------------------------------------------------------------------------
# Gráficos e tabelas
# --------------------------------------------------------------------------
col_esq, col_dir = st.columns([3, 2])

with col_esq:
    st.markdown("**Evolução mensal do ano**")
    resumo = metrics.resumo_mensal_operacao(df_ano)
    grafico = resumo[resumo["Indicador"].isin(["Cargas programadas", "Cargas entregues"])]
    dados_longos = grafico.melt(id_vars="Indicador",
                                value_vars=[c for c in grafico.columns
                                            if c not in ("Indicador", "Total")],
                                var_name="Mês", value_name="Cargas")
    fig = px.bar(dados_longos, x="Mês", y="Cargas", color="Indicador",
                 barmode="group", height=320,
                 color_discrete_sequence=["#4C78A8", "#54A24B"])
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
    st.plotly_chart(fig, width="stretch")

    st.markdown("**Notas fiscais por dia de corte**")
    serie = metrics.serie_diaria(df_mes, ano, mes)
    fig2 = px.bar(serie, x="dia", y="Notas", height=260,
                  color_discrete_sequence=["#E4572E"])
    fig2.update_layout(margin=dict(l=10, r=10, t=20, b=10),
                       xaxis_title="dia de corte")
    st.plotly_chart(fig2, width="stretch")

with col_dir:
    st.markdown("**Status do mês**")
    status_mes = metrics.resumo_por_status(df_mes)
    if status_mes["Cargas"].sum() > 0:
        fig3 = px.pie(status_mes[status_mes["Cargas"] > 0], names="Status",
                      values="Cargas", hole=0.55, height=260,
                      color="Status",
                      color_discrete_map={STATUS[k]: v for k, v in STATUS_CORES.items()})
        fig3.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig3, width="stretch")
    st.dataframe(status_mes, width="stretch", hide_index=True)

    st.markdown("**Ocorrências do mês (notas)**")
    notas_mes = db.listar_notas(modalidade)
    if not notas_mes.empty and not df_mes.empty:
        notas_mes = notas_mes[notas_mes["carga_id"].isin(df_mes["id"])]
    ocorrencias = metrics.resumo_por_ocorrencia(notas_mes)
    if ocorrencias.empty:
        st.caption("Nenhuma ocorrência registrada no mês.")
    else:
        st.dataframe(ocorrencias, width="stretch", hide_index=True)

st.divider()
col_mun, col_cli = st.columns([3, 2])
with col_cli:
    st.markdown("**Clientes com notas pendentes (mês)**")
    ranking = metrics.ranking_clientes(notas_mes)
    if ranking.empty:
        st.caption("Nenhuma nota pendente no mês.")
    else:
        st.dataframe(ranking, width="stretch", hide_index=True)

with col_mun:
    st.markdown("**Desempenho por município (ano)**")
    st.dataframe(metrics.resumo_por_municipio(df_ano), width="stretch",
                 hide_index=True)
