"""Checkout das notas fiscais, agrupado por cliente."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import db, ui
from src.config import MODALIDADES, OCORRENCIAS, STATUS, STATUS_NOTA

ui.configurar_pagina("Checkout", "✅")

modalidade = ui.seletor_modalidade()
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
label_placa = info["doc_label"]
ui.cabecalho(f"✅ Checkout de entrega — {info['label']}",
             "baixa nota a nota, agrupada por cliente")

cargas = db.listar_cargas(modalidade)
if cargas.empty:
    st.info("Nenhuma carga registrada. Importe um arquivo do Wynthor primeiro.")
    st.stop()

# ---------------------------------------------------------------------------
# Escolha da carga: data de corte -> município + placa
# ---------------------------------------------------------------------------
datas = sorted(cargas["data_corte"].dropna().dt.date.unique(), reverse=True)
col_data, col_carga = st.columns([1, 2])
data_escolhida = col_data.selectbox(
    "Data de corte", datas, format_func=lambda d: d.strftime("%d/%m/%Y"))

do_dia = cargas[cargas["data_corte"].dt.date == data_escolhida]
opcoes = do_dia.set_index("id")
rotulo = {i: f"{r['municipio']} · {r['placa'] or 'sem ' + label_placa.lower()}"
              f"  ({r['numcars'] or 'sem carregamento'})"
          for i, r in opcoes.iterrows()}
carga_id = col_carga.selectbox("Carga", list(rotulo.keys()),
                               format_func=lambda i: rotulo[i])

carga = opcoes.loc[carga_id]
notas = db.listar_notas(carga_id=int(carga_id))

if notas.empty:
    st.warning("Esta carga não tem notas importadas.")
    st.stop()

# ---------------------------------------------------------------------------
# Cabeçalho da carga
# ---------------------------------------------------------------------------
total = len(notas)
entregues = int(notas["entregue"].sum())
pendentes = int(notas["pendente"].sum())
com_ocorrencia = int(notas["com_ocorrencia"].sum())
clientes = int(notas["codcli"].nunique())

topo = st.columns(5)
topo[0].metric("Notas", total)
topo[1].metric("Entregues", entregues)
topo[2].metric("Pendentes", pendentes)
topo[3].metric("Com ocorrência", com_ocorrencia)
topo[4].metric("Checkout", f"{(total - pendentes) / total * 100:.0f}%")

st.caption(
    f"Corte {data_escolhida:%d/%m/%Y} · {carga['municipio']}/{carga['uf']} · "
    f"{label_placa}: {carga['placa'] or '—'} · Carregamento(s): "
    f"{carga['numcars'] or '—'} · Status da carga: **{STATUS.get(carga['status'], '—')}**"
)
st.progress((total - pendentes) / total)

data_checkout = st.date_input("Data do checkout", value=date.today(),
                              format="DD/MM/YYYY", key="data_checkout")

# ---------------------------------------------------------------------------
# Ações em massa
# ---------------------------------------------------------------------------
with st.expander("⚡ Ação para a carga inteira"):
    col_a, col_b, col_c = st.columns([1, 2, 1])
    status_massa = col_a.selectbox("Status", list(STATUS_NOTA.keys()),
                                   format_func=lambda k: STATUS_NOTA[k],
                                   index=1, key="status_massa")
    ocorr_massa = col_b.selectbox("Ocorrência", OCORRENCIAS, key="ocorr_massa")
    col_c.write("")
    if col_c.button("Aplicar a todas", key="btn_massa"):
        alterados = db.checkout_notas(notas["id"].tolist(), status_massa,
                                      ocorr_massa, data_checkout)
        db.recalcular_status_carga(int(carga_id))
        st.success(f"{alterados} nota(s) atualizada(s).")
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Checkout por cliente
# ---------------------------------------------------------------------------
por_cliente = db.notas_por_cliente(int(carga_id))
filtro = st.radio("Mostrar", ["Todos", "Só pendentes", "Só com ocorrência"],
                  horizontal=True)

st.markdown(f"**{len(por_cliente)} cliente(s) nesta carga**")

for _, linha_cliente in por_cliente.iterrows():
    codcli = linha_cliente["codcli"]
    do_cliente = notas[notas["codcli"] == codcli]

    if filtro == "Só pendentes" and not do_cliente["pendente"].any():
        continue
    if filtro == "Só com ocorrência" and not do_cliente["com_ocorrencia"].any():
        continue

    if linha_cliente["Pendentes"] == 0:
        marca = "🟢" if linha_cliente["Ocorrências"] == 0 else "🟠"
    elif linha_cliente["Pendentes"] == linha_cliente["Notas"]:
        marca = "⚪"
    else:
        marca = "🔵"

    titulo = (f"{marca} {linha_cliente['cliente']} · cód. {codcli} — "
              f"{int(linha_cliente['Entregues'])}/{int(linha_cliente['Notas'])} nota(s) entregue(s)")

    with st.expander(titulo, expanded=(filtro != "Todos")):
        col_s, col_o, col_btn = st.columns([1, 2, 1])
        status_cli = col_s.selectbox("Status", list(STATUS_NOTA.keys()),
                                     format_func=lambda k: STATUS_NOTA[k], index=1,
                                     key=f"status_{codcli}")
        ocorr_cli = col_o.selectbox("Ocorrência", OCORRENCIAS, key=f"ocorr_{codcli}")
        col_btn.write("")
        if col_btn.button("Aplicar ao cliente", key=f"btn_{codcli}"):
            db.checkout_notas(do_cliente["id"].tolist(), status_cli,
                              ocorr_cli, data_checkout)
            db.recalcular_status_carga(int(carga_id))
            st.rerun()

        visao = do_cliente[["id", "numcar", "numnota", "status", "ocorrencia",
                            "data_checkout", "observacao"]].rename(columns={
            "id": "ID", "numcar": "Carregamento", "numnota": "Nota fiscal",
            "status": "Status", "ocorrencia": "Ocorrência",
            "data_checkout": "Data checkout", "observacao": "Observação",
        })
        editado = st.data_editor(
            visao, width="stretch", hide_index=True, num_rows="fixed",
            disabled=["ID", "Carregamento", "Nota fiscal"],
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    options=list(STATUS_NOTA.keys()), required=True),
                "Ocorrência": st.column_config.SelectboxColumn(options=OCORRENCIAS),
                "Data checkout": st.column_config.DateColumn(format="DD/MM/YYYY"),
            },
            key=f"editor_{codcli}",
        )

        if st.button("💾 Salvar notas deste cliente", key=f"salvar_{codcli}"):
            for _, nota in editado.iterrows():
                original = visao[visao["ID"] == nota["ID"]].iloc[0]
                if nota.equals(original):
                    continue
                data_nota = nota["Data checkout"]
                if pd.isna(data_nota) and nota["Status"] != "P":
                    data_nota = data_checkout
                db.salvar_nota({
                    "status": nota["Status"],
                    "ocorrencia": nota["Ocorrência"] or "Sem ocorrência",
                    "data_checkout": None if nota["Status"] == "P" else data_nota,
                    "observacao": nota["Observação"] or None,
                }, nota_id=int(nota["ID"]))
            db.recalcular_status_carga(int(carga_id))
            st.success("Notas atualizadas.")
            st.rerun()

st.divider()
st.download_button(
    "Baixar checkout desta carga (CSV)",
    notas[["numcar", "numnota", "codcli", "cliente", "status", "ocorrencia",
           "data_checkout", "observacao"]].to_csv(index=False, sep=";",
                                                  encoding="utf-8-sig"),
    file_name=f"checkout_{carga['municipio']}_{data_escolhida:%Y%m%d}.csv",
    mime="text/csv",
)
