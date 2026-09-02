"""Programação de cortes — lança a carga no cronograma antes de ter o arquivo.

O corte é definido no dia, mas o Wynthor só disponibiliza os dados depois do
faturamento (em geral um dia antes da entrega). Aqui você registra o corte do
município na hora em que ele acontece: a carga já entra no cronograma como
"Programado", e quando o arquivo chegar a importação encaixa as notas nessa
mesma carga — sem duplicar.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src import db, ui
from src.config import MODALIDADES, PRAZO_PADRAO_DIAS, STATUS, UFS

ui.configurar_pagina("Programar cortes", "🗓️")

modalidade = ui.seletor_modalidade()
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
label_placa = info["doc_label"]
ui.cabecalho(f"🗓️ Programar cortes — {info['label']}",
             "registre o corte antes de o Wynthor liberar os dados")

cadastro = db.listar_municipios(modalidade, somente_ativos=True)
if cadastro.empty:
    st.warning("Cadastre municípios desta modalidade em **Cadastros** para "
               "programar os cortes.")
    st.stop()

prazos = dict(zip(cadastro["nome"], cadastro["prazo_dias"]))
ufs_por_municipio = dict(zip(cadastro["nome"], cadastro["uf"]))

# ---------------------------------------------------------------------------
# Novo corte
# ---------------------------------------------------------------------------
st.subheader("Novo corte")

col1, col2 = st.columns([1, 2])
data_corte = col1.date_input("Data de corte", value=date.today(),
                             format="DD/MM/YYYY")
municipios_escolhidos = col2.multiselect(
    "Município(s) cortados nesta data", cadastro["nome"].tolist(),
    help="Pode marcar vários de uma vez — cada um vira uma carga programada.",
)

col3, col4, col5 = st.columns(3)
dias_prazo = col3.number_input("Prazo de entrega (dias após o corte)",
                               min_value=0, value=PRAZO_PADRAO_DIAS)
placa = col4.text_input(f"{label_placa} (se já souber)",
                        help="Pode deixar em branco: a importação preenche com "
                             "a placa que vier do Wynthor.")
observacao = col5.text_input("Observação")

if st.button("🗓️ Programar corte", type="primary", disabled=not municipios_escolhidos):
    criadas, existentes = [], []
    for municipio in municipios_escolhidos:
        if db.buscar_carga(modalidade, data_corte, municipio, placa.strip().upper()):
            existentes.append(municipio)
            continue
        db.salvar_carga({
            "modalidade": modalidade,
            "data_corte": data_corte,
            "municipio": municipio,
            "placa": placa.strip().upper(),
            "uf": ufs_por_municipio.get(municipio, "AM"),
            "previsao_entrega": data_corte + timedelta(days=int(dias_prazo)),
            "status": "P",
            "ocorrencia": "Sem ocorrência",
            "observacao": observacao or None,
            "origem_dado": "programado",
        })
        criadas.append(municipio)

    if criadas:
        st.success(f"Corte de {data_corte:%d/%m/%Y} programado para: "
                   + ", ".join(criadas))
    if existentes:
        st.info("Já existia programação para: " + ", ".join(existentes))
    st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Programações aguardando o arquivo
# ---------------------------------------------------------------------------
st.subheader("Cortes aguardando o arquivo do Wynthor")

abertas = db.listar_programacoes_abertas(modalidade)
if abertas.empty:
    st.caption("Nenhum corte programado sem notas. Tudo que foi cortado já "
               "recebeu o arquivo.")
else:
    visao = abertas[["id", "data_corte", "municipio", "placa", "uf",
                     "previsao_entrega", "status", "observacao"]].copy()
    visao["Atraso"] = (pd.Timestamp(date.today()) - visao["data_corte"]).dt.days
    visao = visao.rename(columns={
        "id": "ID", "data_corte": "Corte", "municipio": "Município",
        "placa": label_placa, "uf": "UF", "previsao_entrega": "Previsão",
        "status": "Status", "observacao": "Observação",
    })

    st.dataframe(
        visao, width="stretch", hide_index=True,
        column_config={
            "Corte": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Previsão": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Status": st.column_config.TextColumn(help="P = Programado"),
            "Atraso": st.column_config.NumberColumn(
                help="dias desde o corte sem o arquivo importado", format="%d d"),
        },
    )

    antigas = visao[visao["Atraso"] > 3]
    if not antigas.empty:
        st.warning(f"{len(antigas)} corte(s) com mais de 3 dias sem arquivo "
                   "importado: " + ", ".join(antigas["Município"].tolist()))

    with st.expander("🗑️ Cancelar uma programação"):
        alvo = st.selectbox(
            "Programação", visao["ID"].tolist(),
            format_func=lambda i: (
                f"{visao.loc[visao['ID'] == i, 'Corte'].iloc[0]:%d/%m/%Y} · "
                f"{visao.loc[visao['ID'] == i, 'Município'].iloc[0]}"),
        )
        if st.button("Confirmar cancelamento"):
            db.excluir_carga(int(alvo))
            st.success("Programação cancelada.")
            st.rerun()

st.divider()
st.caption(
    "Como funciona o encaixe: quando você importar o arquivo do Wynthor com "
    "esta **mesma data de corte** e o mesmo município, as notas entram nesta "
    f"carga. Se a programação estiver sem {label_placa.lower()}, a que vier do "
    "arquivo é gravada nela automaticamente."
)
