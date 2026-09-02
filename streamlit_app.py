"""Checkout de entregas — tela inicial do sistema.

Tabela de clientes da carga, no estilo planilha: cada linha é um cliente e o
que você marcar nela vale para todas as notas fiscais daquele cliente.
Clientes com mais de uma nota podem ser abertos nota a nota logo abaixo.

Execute com:  streamlit run streamlit_app.py
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import db, ui
from src.config import MODALIDADES, OCORRENCIAS, STATUS, STATUS_NOTA

MISTO = "— misto —"
NOMES_STATUS = list(STATUS_NOTA.values())
CODIGO_POR_NOME = {v: k for k, v in STATUS_NOTA.items()}

ui.configurar_pagina("Checkout", "✅")

modalidade = ui.seletor_modalidade()
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
label_placa = info["doc_label"]
ui.cabecalho(f"✅ Checkout de entregas — {info['label']}",
             "uma linha por cliente: marque o status e salve")

cargas = db.listar_cargas(modalidade)
if cargas.empty:
    st.info("Nenhuma carga registrada nesta modalidade. Comece pela página "
            "**Importar Wynthor** para trazer as notas do carregamento.")
    st.stop()

# ---------------------------------------------------------------------------
# Escolha da carga
# ---------------------------------------------------------------------------
datas = sorted(cargas["data_corte"].dropna().dt.date.unique(), reverse=True)
col_data, col_carga = st.columns([1, 2])
data_escolhida = col_data.selectbox("Data de corte", datas,
                                    format_func=lambda d: d.strftime("%d/%m/%Y"))

do_dia = cargas[cargas["data_corte"].dt.date == data_escolhida].set_index("id")
rotulo = {}
for identificador, linha in do_dia.iterrows():
    placa = linha["placa"] or f"sem {label_placa.lower()}"
    pendentes = int(linha.get("notas_pendentes", 0) or 0)
    rotulo[identificador] = (f"{linha['municipio']} · {placa} "
                             + (f"— {pendentes} pendente(s)" if pendentes else "— concluída"))

carga_id = int(col_carga.selectbox("Carga", list(rotulo.keys()),
                                   format_func=lambda i: rotulo[i]))
carga = do_dia.loc[carga_id]
notas = db.listar_notas(carga_id=carga_id)

if notas.empty:
    st.warning("Esta carga não tem notas importadas.")
    st.stop()

# ---------------------------------------------------------------------------
# Situação da carga
# ---------------------------------------------------------------------------
total = len(notas)
pendentes = int(notas["pendente"].sum())

topo = st.columns(5)
topo[0].metric("Notas", total)
topo[1].metric("Clientes", int(notas["codcli"].nunique()))
topo[2].metric("Entregues", int(notas["entregue"].sum()))
topo[3].metric("Pendentes", pendentes)
topo[4].metric("Checkout", f"{(total - pendentes) / total * 100:.0f}%")

st.caption(
    f"Corte {data_escolhida:%d/%m/%Y} · {carga['municipio']}/{carga['uf']} · "
    f"{label_placa}: {carga['placa'] or '—'} · Carregamento(s): "
    f"{carga['numcars'] or '—'} · Status: **{STATUS.get(carga['status'], '—')}**"
)
st.progress((total - pendentes) / total)

# ---------------------------------------------------------------------------
# Monta a tabela: uma linha por cliente
# ---------------------------------------------------------------------------
linhas = []
for (codcli, cliente), grupo in notas.groupby(["codcli", "cliente"], dropna=False):
    status_unicos = grupo["status"].unique()
    ocorr_unicas = [o for o in grupo["ocorrencia"].fillna("Sem ocorrência").unique()]
    datas_checkout = grupo["data_checkout"].dropna()
    observacoes = [o for o in grupo["observacao"].dropna().unique() if str(o).strip()]

    linhas.append({
        "Cód.": str(codcli),
        "Cliente": str(cliente),
        "NFs": int(len(grupo)),
        "Notas fiscais": ", ".join(sorted(grupo["numnota"].astype(str))),
        "Status": (STATUS_NOTA.get(status_unicos[0], "Pendente")
                   if len(status_unicos) == 1 else MISTO),
        "Ocorrência": (ocorr_unicas[0] if len(ocorr_unicas) == 1 else MISTO),
        "Data checkout": (datas_checkout.max().date() if not datas_checkout.empty else None),
        "Observação": observacoes[0] if len(observacoes) == 1 else "",
    })

tabela = pd.DataFrame(linhas).sort_values("Cliente").reset_index(drop=True)

# ---------------------------------------------------------------------------
# Filtros e ações rápidas
# ---------------------------------------------------------------------------
col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
busca = col_f1.text_input("Buscar cliente ou código", placeholder="ex.: MERCADINHO ou 815465")
filtro = col_f2.selectbox("Mostrar", ["Todos", "Só pendentes", "Só com ocorrência"])
data_checkout = col_f3.date_input("Data do checkout", value=date.today(),
                                  format="DD/MM/YYYY")

visivel = tabela.copy()
if busca.strip():
    termo = busca.strip().upper()
    visivel = visivel[visivel["Cliente"].str.upper().str.contains(termo)
                      | visivel["Cód."].str.contains(termo)]
if filtro == "Só pendentes":
    codigos = notas.loc[notas["pendente"], "codcli"].astype(str).unique()
    visivel = visivel[visivel["Cód."].isin(codigos)]
elif filtro == "Só com ocorrência":
    codigos = notas.loc[notas["com_ocorrencia"], "codcli"].astype(str).unique()
    visivel = visivel[visivel["Cód."].isin(codigos)]

if visivel.empty:
    st.success("Nenhum cliente nesse filtro.")
    st.stop()

st.markdown(f"**{len(visivel)} cliente(s)** — edite as colunas Status, Ocorrência "
            "e Observação e clique em salvar. O que você marcar vale para todas "
            "as notas do cliente.")

editado = st.data_editor(
    visivel, width="stretch", hide_index=True, num_rows="fixed",
    disabled=["Cód.", "Cliente", "NFs", "Notas fiscais"],
    column_config={
        "Cód.": st.column_config.TextColumn(width="small"),
        "Cliente": st.column_config.TextColumn(width="large"),
        "NFs": st.column_config.NumberColumn(width="small", help="quantidade de notas"),
        "Notas fiscais": st.column_config.TextColumn(width="medium"),
        "Status": st.column_config.SelectboxColumn(
            options=NOMES_STATUS + [MISTO], required=True, width="medium"),
        "Ocorrência": st.column_config.SelectboxColumn(
            options=OCORRENCIAS + [MISTO], width="medium"),
        "Data checkout": st.column_config.DateColumn(format="DD/MM/YYYY", width="small"),
        "Observação": st.column_config.TextColumn(width="medium"),
    },
    key=f"editor_clientes_{carga_id}",
)

col_salvar, col_todos, col_vazio = st.columns([1, 1, 2])

if col_salvar.button("💾 Salvar checkout", type="primary"):
    alterados = 0
    for _, linha in editado.iterrows():
        original = visivel[visivel["Cód."] == linha["Cód."]].iloc[0]
        if linha.equals(original):
            continue

        ids = notas.loc[notas["codcli"].astype(str) == linha["Cód."], "id"].tolist()
        status_nome = linha["Status"]
        if status_nome == MISTO:  # não mexeu no status: mantém o de cada nota
            valores_extras = {}
            if linha["Ocorrência"] != MISTO:
                valores_extras["ocorrencia"] = linha["Ocorrência"]
            if str(linha["Observação"] or "") != str(original["Observação"] or ""):
                valores_extras["observacao"] = linha["Observação"] or None
            for nota_id in ids:
                if valores_extras:
                    db.salvar_nota(valores_extras, nota_id=int(nota_id))
            alterados += len(ids) if valores_extras else 0
            continue

        data_aplicada = linha["Data checkout"] or data_checkout
        ocorrencia = (linha["Ocorrência"] if linha["Ocorrência"] != MISTO
                      else "Sem ocorrência")
        alterados += db.checkout_notas(ids, CODIGO_POR_NOME[status_nome],
                                       ocorrencia, data_aplicada,
                                       observacao=linha["Observação"] or None)

    db.recalcular_status_carga(carga_id)
    if alterados:
        st.success(f"{alterados} nota(s) atualizada(s).")
    else:
        st.info("Nada mudou na tabela.")
    st.rerun()

if col_todos.button("✅ Marcar visíveis como entregues"):
    ids = notas.loc[notas["codcli"].astype(str).isin(visivel["Cód."]), "id"].tolist()
    db.checkout_notas(ids, "E", "Sem ocorrência", data_checkout)
    db.recalcular_status_carga(carga_id)
    st.rerun()

# ---------------------------------------------------------------------------
# Detalhe nota a nota (quando o cliente tem notas em situações diferentes)
# ---------------------------------------------------------------------------
st.divider()
with st.expander("🔍 Ajustar nota a nota (um cliente por vez)"):
    multiplos = tabela[tabela["NFs"] > 1]
    escolha = st.selectbox(
        "Cliente", tabela["Cód."].tolist(),
        format_func=lambda c: f"{tabela.loc[tabela['Cód.'] == c, 'Cliente'].iloc[0]} "
                              f"({tabela.loc[tabela['Cód.'] == c, 'NFs'].iloc[0]} NF)",
    )
    do_cliente = notas[notas["codcli"].astype(str) == escolha]
    detalhe = do_cliente[["id", "numcar", "numnota", "status", "ocorrencia",
                          "data_checkout", "observacao"]].rename(columns={
        "id": "ID", "numcar": "Carregamento", "numnota": "Nota fiscal",
        "status": "Status", "ocorrencia": "Ocorrência",
        "data_checkout": "Data checkout", "observacao": "Observação",
    })
    detalhe["Status"] = detalhe["Status"].map(STATUS_NOTA)

    detalhe_editado = st.data_editor(
        detalhe, width="stretch", hide_index=True, num_rows="fixed",
        disabled=["ID", "Carregamento", "Nota fiscal"],
        column_config={
            "Status": st.column_config.SelectboxColumn(options=NOMES_STATUS,
                                                       required=True),
            "Ocorrência": st.column_config.SelectboxColumn(options=OCORRENCIAS),
            "Data checkout": st.column_config.DateColumn(format="DD/MM/YYYY"),
        },
        key=f"editor_notas_{carga_id}_{escolha}",
    )

    if st.button("💾 Salvar notas deste cliente"):
        for _, nota in detalhe_editado.iterrows():
            original = detalhe[detalhe["ID"] == nota["ID"]].iloc[0]
            if nota.equals(original):
                continue
            codigo = CODIGO_POR_NOME[nota["Status"]]
            data_nota = nota["Data checkout"]
            if pd.isna(data_nota) and codigo != "P":
                data_nota = data_checkout
            db.salvar_nota({
                "status": codigo,
                "ocorrencia": nota["Ocorrência"] or "Sem ocorrência",
                "data_checkout": None if codigo == "P" else data_nota,
                "observacao": nota["Observação"] or None,
            }, nota_id=int(nota["ID"]))
        db.recalcular_status_carga(carga_id)
        st.rerun()

# ---------------------------------------------------------------------------
# Correção da carga e exportação
# ---------------------------------------------------------------------------
with st.expander("🛠️ Corrigir ou excluir esta carga"):
    st.caption("Use se a importação foi feita com data de corte, município ou "
               f"{label_placa.lower()} errados.")
    c1, c2, c3 = st.columns(3)
    nova_data = c1.date_input("Data de corte", value=data_escolhida,
                              format="DD/MM/YYYY", key="corrige_data")
    novo_municipio = c2.text_input("Município", value=carga["municipio"],
                                   key="corrige_mun")
    nova_placa = c3.text_input(label_placa, value=carga["placa"] or "",
                               key="corrige_placa")
    if st.button("Salvar correção"):
        db.salvar_carga({"data_corte": nova_data,
                         "municipio": novo_municipio.strip(),
                         "placa": nova_placa.strip().upper()}, carga_id=carga_id)
        st.rerun()

    st.divider()
    if st.checkbox("Confirmo que quero excluir esta carga e todas as suas notas"):
        if st.button("🗑️ Excluir carga"):
            db.excluir_carga(carga_id)
            st.rerun()

st.download_button(
    "⬇️ Baixar checkout desta carga (CSV para Excel)",
    tabela.to_csv(index=False, sep=";", encoding="utf-8-sig"),
    file_name=f"checkout_{carga['municipio']}_{data_escolhida:%Y%m%d}.csv",
    mime="text/csv",
)
