"""Checkout de entregas — tela inicial do sistema.

Checklist: marque a caixa "Entregue" do cliente e salve. A data e a hora são
carimbadas automaticamente. Se houve problema, escolha a ocorrência — sem
marcar como entregue, a nota fica registrada como não entregue.

Execute com:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import db, ui
from src.config import MODALIDADES, OCORRENCIAS, STATUS, STATUS_NOTA, agora

MISTO = "— misto —"
NOMES_STATUS = list(STATUS_NOTA.values())
CODIGO_POR_NOME = {v: k for k, v in STATUS_NOTA.items()}

ui.configurar_pagina("Checkout", "✅")

modalidade = ui.seletor_modalidade()
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
label_placa = info["doc_label"]
ui.cabecalho(f"✅ Checkout de entregas — {info['label']}",
             "marque o que foi entregue e salve — a data e a hora entram sozinhas")

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
    st.warning("Esta carga ainda não recebeu notas do Wynthor.")
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
# Uma linha por cliente
# ---------------------------------------------------------------------------
linhas = []
for (codcli, cliente), grupo in notas.groupby(["codcli", "cliente"], dropna=False):
    status_unicos = list(grupo["status"].unique())
    ocorr_unicas = list(grupo["ocorrencia"].fillna("Sem ocorrência").unique())
    momentos = grupo["checkout_em"].dropna()
    observacoes = [o for o in grupo["observacao"].dropna().unique() if str(o).strip()]

    linhas.append({
        "✔": bool(len(status_unicos) == 1 and status_unicos[0] == "E"),
        "Cód.": str(codcli),
        "Cliente": str(cliente),
        "NFs": int(len(grupo)),
        "Notas fiscais": ", ".join(sorted(grupo["numnota"].astype(str))),
        "Ocorrência": ocorr_unicas[0] if len(ocorr_unicas) == 1 else MISTO,
        "Checkout": momentos.max() if not momentos.empty else pd.NaT,
        "Situação": (STATUS_NOTA.get(status_unicos[0], "Pendente")
                     if len(status_unicos) == 1 else MISTO),
        "Observação": observacoes[0] if len(observacoes) == 1 else "",
    })

tabela = pd.DataFrame(linhas).sort_values("Cliente").reset_index(drop=True)

# ---------------------------------------------------------------------------
# Busca e filtro
# ---------------------------------------------------------------------------
col_f1, col_f2 = st.columns([3, 1])
busca = col_f1.text_input(
    "Buscar por nota fiscal, cliente ou código",
    placeholder="ex.: 450055, MERCADINHO ou 815465")
filtro = col_f2.selectbox("Mostrar", ["Todos", "Só pendentes", "Só com ocorrência"])

visivel = tabela.copy()
if busca.strip():
    termo = busca.strip().upper()
    por_nota = (notas.loc[notas["numnota"].astype(str).str.contains(termo, na=False),
                          "codcli"].astype(str).unique())
    visivel = visivel[
        visivel["Cliente"].str.upper().str.contains(termo, regex=False)
        | visivel["Cód."].str.contains(termo, regex=False)
        | visivel["Cód."].isin(por_nota)
    ]
if filtro == "Só pendentes":
    codigos = notas.loc[notas["pendente"], "codcli"].astype(str).unique()
    visivel = visivel[visivel["Cód."].isin(codigos)]
elif filtro == "Só com ocorrência":
    codigos = notas.loc[notas["com_ocorrencia"], "codcli"].astype(str).unique()
    visivel = visivel[visivel["Cód."].isin(codigos)]

if visivel.empty:
    st.success("Nenhum cliente nesse filtro.")
    st.stop()

st.markdown(f"**{len(visivel)} cliente(s)** — marque a caixa dos entregues e "
            "clique em salvar. Para quem teve problema, escolha a ocorrência e "
            "deixe a caixa desmarcada.")

editado = st.data_editor(
    visivel, width="stretch", hide_index=True, num_rows="fixed",
    disabled=["Cód.", "Cliente", "NFs", "Notas fiscais", "Checkout", "Situação"],
    column_config={
        "✔": st.column_config.CheckboxColumn(
            "Entregue", width="small", help="marque quando o cliente receber"),
        "Cód.": st.column_config.TextColumn(width="small"),
        "Cliente": st.column_config.TextColumn(width="large"),
        "NFs": st.column_config.NumberColumn(width="small", help="quantidade de notas"),
        "Notas fiscais": st.column_config.TextColumn(width="medium"),
        "Ocorrência": st.column_config.SelectboxColumn(
            options=OCORRENCIAS + [MISTO], width="medium"),
        "Checkout": st.column_config.DatetimeColumn(
            format="DD/MM/YYYY HH:mm", width="medium",
            help="preenchido automaticamente ao salvar"),
        "Situação": st.column_config.TextColumn(width="small"),
        "Observação": st.column_config.TextColumn(width="medium"),
    },
    key=f"editor_clientes_{carga_id}",
)

col_salvar, col_todos, _ = st.columns([1, 1, 2])

if col_salvar.button("💾 Salvar checkout", type="primary"):
    momento = agora()
    alterados = 0

    for _, linha in editado.iterrows():
        original = visivel[visivel["Cód."] == linha["Cód."]].iloc[0]
        mudou_marca = bool(linha["✔"]) != bool(original["✔"])
        mudou_ocorrencia = linha["Ocorrência"] != original["Ocorrência"]
        mudou_obs = str(linha["Observação"] or "") != str(original["Observação"] or "")
        if not (mudou_marca or mudou_ocorrencia or mudou_obs):
            continue

        ids = notas.loc[notas["codcli"].astype(str) == linha["Cód."], "id"].tolist()
        ocorrencia = (linha["Ocorrência"] if linha["Ocorrência"] != MISTO
                      else "Sem ocorrência")

        if linha["✔"]:
            novo_status = "E"                       # entregue
        elif ocorrencia != "Sem ocorrência":
            novo_status = "D"                       # não entregue, com ocorrência
        else:
            novo_status = "P"                       # segue pendente

        alterados += db.checkout_notas(
            ids, novo_status, ocorrencia,
            observacao=linha["Observação"] or None, momento=momento)

    db.recalcular_status_carga(carga_id)
    if alterados:
        st.success(f"{alterados} nota(s) registrada(s) em "
                   f"{momento:%d/%m/%Y às %H:%M}.")
    else:
        st.info("Nada mudou na tabela.")
    st.rerun()

if col_todos.button("✅ Marcar visíveis como entregues"):
    ids = notas.loc[notas["codcli"].astype(str).isin(visivel["Cód."]), "id"].tolist()
    db.checkout_notas(ids, "E", "Sem ocorrência")
    db.recalcular_status_carga(carga_id)
    st.rerun()

# ---------------------------------------------------------------------------
# Detalhe nota a nota
# ---------------------------------------------------------------------------
st.divider()
with st.expander("🔍 Ajustar nota a nota (quando só parte das notas do cliente foi entregue)"):
    escolha = st.selectbox(
        "Cliente", tabela["Cód."].tolist(),
        format_func=lambda c: f"{tabela.loc[tabela['Cód.'] == c, 'Cliente'].iloc[0]} "
                              f"({tabela.loc[tabela['Cód.'] == c, 'NFs'].iloc[0]} NF)",
    )
    do_cliente = notas[notas["codcli"].astype(str) == escolha]
    detalhe = do_cliente[["id", "numcar", "numnota", "status", "ocorrencia",
                          "checkout_em", "observacao"]].rename(columns={
        "id": "ID", "numcar": "Carregamento", "numnota": "Nota fiscal",
        "status": "Situação", "ocorrencia": "Ocorrência",
        "checkout_em": "Checkout", "observacao": "Observação",
    })
    detalhe["Situação"] = detalhe["Situação"].map(STATUS_NOTA)

    detalhe_editado = st.data_editor(
        detalhe, width="stretch", hide_index=True, num_rows="fixed",
        disabled=["ID", "Carregamento", "Nota fiscal", "Checkout"],
        column_config={
            "Situação": st.column_config.SelectboxColumn(options=NOMES_STATUS,
                                                         required=True),
            "Ocorrência": st.column_config.SelectboxColumn(options=OCORRENCIAS),
            "Checkout": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
        },
        key=f"editor_notas_{carga_id}_{escolha}",
    )

    if st.button("💾 Salvar notas deste cliente"):
        momento = agora()
        for _, nota in detalhe_editado.iterrows():
            original = detalhe[detalhe["ID"] == nota["ID"]].iloc[0]
            if nota.equals(original):
                continue
            db.checkout_notas([int(nota["ID"])], CODIGO_POR_NOME[nota["Situação"]],
                              nota["Ocorrência"] or "Sem ocorrência",
                              observacao=nota["Observação"] or None, momento=momento)
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

exportar = notas[["numcar", "numnota", "codcli", "cliente", "status",
                  "ocorrencia", "checkout_em", "observacao"]].copy()
exportar["status"] = exportar["status"].map(STATUS_NOTA)
st.download_button(
    "⬇️ Baixar checkout desta carga (CSV para Excel)",
    exportar.to_csv(index=False, sep=";", encoding="utf-8-sig"),
    file_name=f"checkout_{carga['municipio']}_{data_escolhida:%Y%m%d}.csv",
    mime="text/csv",
)
