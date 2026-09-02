"""Cargas do período: criação manual, edição e acompanhamento do checkout."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src import db, ui
from src.config import (MODALIDADES, OCORRENCIAS, PRAZO_PADRAO_DIAS, STATUS,
                        UFS)

ui.configurar_pagina("Cargas", "🧾")

modalidade = ui.seletor_modalidade()
ano, mes = ui.seletor_periodo(modalidade)
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
label_placa = info["doc_label"]
ui.cabecalho(f"{info['icone']} Cargas — {info['label']}",
             f"a carga é identificada por data de corte + município + {label_placa.lower()}")

cadastro_mun = db.listar_municipios(modalidade)
municipios = cadastro_mun["nome"].tolist() if not cadastro_mun.empty else []
prazos = (dict(zip(cadastro_mun["nome"], cadastro_mun["prazo_dias"]))
          if not cadastro_mun.empty else {})
transportadoras = db.listar_transportadoras(modalidade)
lista_transp = transportadoras["nome"].tolist() if not transportadoras.empty else []
veiculos = db.listar_veiculos(modalidade)
lista_placas = (veiculos["identificacao"].dropna().unique().tolist()
                if not veiculos.empty else [])

aba_nova, aba_lista = st.tabs(["➕ Nova carga", "📋 Cargas do período"])

# ---------------------------------------------------------------------------
# Nova carga (manual — sem notas; as notas vêm da importação)
# ---------------------------------------------------------------------------
with aba_nova:
    st.caption("Use para lançar uma viagem que não veio do Wynthor. "
               "As notas fiscais entram pela página de importação.")
    with st.form("form_nova_carga", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_corte = c1.date_input("Data de corte", value=date.today(),
                                   format="DD/MM/YYYY")
        municipio = (c2.selectbox("Município", municipios + ["— outro —"])
                     if municipios else c2.text_input("Município"))
        placa = (c3.selectbox(label_placa, [""] + lista_placas)
                 if lista_placas else c3.text_input(label_placa))

        if municipio == "— outro —":
            municipio = st.text_input("Digite o município")

        c4, c5, c6 = st.columns(3)
        uf = c4.selectbox("UF", UFS, index=0)
        transportadora = c5.selectbox("Transportadora", ["—"] + lista_transp)
        motorista = c6.text_input("Motorista / responsável")

        c7, c8, c9 = st.columns(3)
        prazo = int(prazos.get(municipio, PRAZO_PADRAO_DIAS) or PRAZO_PADRAO_DIAS)
        previsao = c7.date_input("Previsão de entrega",
                                 value=data_corte + timedelta(days=prazo),
                                 format="DD/MM/YYYY")
        peso_kg = c8.number_input("Peso (kg)", min_value=0.0, step=1.0, format="%.3f")
        valor = c9.number_input("Valor (R$)", min_value=0.0, step=100.0, format="%.2f")

        observacao = st.text_input("Observação")

        if st.form_submit_button("Salvar carga", type="primary"):
            if not municipio:
                st.error("Informe o município.")
            elif db.buscar_carga(modalidade, data_corte, municipio, placa or ""):
                st.error("Já existe uma carga com essa data de corte, município e "
                         f"{label_placa.lower()}.")
            else:
                db.salvar_carga({
                    "modalidade": modalidade,
                    "data_corte": data_corte,
                    "municipio": municipio,
                    "placa": (placa or "").upper(),
                    "uf": uf,
                    "transportadora": None if transportadora == "—" else transportadora,
                    "motorista": motorista or None,
                    "previsao_entrega": previsao,
                    "status": "P",
                    "ocorrencia": "Sem ocorrência",
                    "observacao": observacao or None,
                    "peso_kg": float(peso_kg),
                    "valor": float(valor),
                    "origem_dado": "manual",
                })
                db.sincronizar_municipio(modalidade, municipio, uf)
                st.success(f"Carga de {municipio} registrada.")

# ---------------------------------------------------------------------------
# Lista / edição
# ---------------------------------------------------------------------------
with aba_lista:
    df = db.listar_cargas(modalidade, ano=ano, mes=mes)
    if df.empty:
        st.info("Nenhuma carga no período selecionado.")
        st.stop()

    filtro_status = st.multiselect("Filtrar por status", list(STATUS.keys()),
                                   format_func=lambda k: STATUS[k], default=[])
    if filtro_status:
        df = df[df["status"].isin(filtro_status)]

    visao = df[["id", "data_corte", "municipio", "placa", "uf", "numcars",
                "transportadora", "motorista", "notas_total", "notas_entregues",
                "notas_pendentes", "checkout_pct", "peso_kg", "valor",
                "previsao_entrega", "data_entrega", "status", "ocorrencia",
                "dias_atraso", "observacao"]].copy()
    visao = visao.rename(columns={
        "id": "ID", "data_corte": "Corte", "municipio": "Município",
        "placa": label_placa, "uf": "UF", "numcars": "Carregamentos",
        "transportadora": "Transportadora", "motorista": "Motorista",
        "notas_total": "Notas", "notas_entregues": "Entregues",
        "notas_pendentes": "Pendentes", "checkout_pct": "Checkout %",
        "peso_kg": "Peso (kg)", "valor": "Valor (R$)",
        "previsao_entrega": "Previsão", "data_entrega": "Entrega",
        "status": "Status", "ocorrencia": "Ocorrência",
        "dias_atraso": "Dias atraso", "observacao": "Observação",
    })

    st.caption("O status, as datas de entrega e as ocorrências são atualizados "
               "automaticamente pelo checkout das notas.")

    editado = st.data_editor(
        visao, width="stretch", hide_index=True, num_rows="fixed",
        disabled=["ID", "Carregamentos", "Notas", "Entregues", "Pendentes",
                  "Checkout %", "Dias atraso"],
        column_config={
            "Corte": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Previsão": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Entrega": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Status": st.column_config.SelectboxColumn(options=list(STATUS.keys())),
            "Ocorrência": st.column_config.SelectboxColumn(options=OCORRENCIAS),
            "Checkout %": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.0f%%"),
            "Peso (kg)": st.column_config.NumberColumn(format="%.3f"),
            "Valor (R$)": st.column_config.NumberColumn(format="%.2f"),
        },
        key="editor_cargas",
    )

    col_salvar, col_excluir = st.columns([1, 2])
    if col_salvar.button("💾 Salvar alterações", type="primary"):
        alteracoes = 0
        for _, linha in editado.iterrows():
            original = visao[visao["ID"] == linha["ID"]].iloc[0]
            if linha.equals(original):
                continue
            db.salvar_carga({
                "data_corte": linha["Corte"],
                "municipio": linha["Município"],
                "placa": (linha[label_placa] or "").upper(),
                "uf": linha["UF"],
                "transportadora": linha["Transportadora"],
                "motorista": linha["Motorista"],
                "peso_kg": float(linha["Peso (kg)"] or 0),
                "valor": float(linha["Valor (R$)"] or 0),
                "previsao_entrega": linha["Previsão"],
                "data_entrega": linha["Entrega"],
                "status": linha["Status"],
                "ocorrencia": linha["Ocorrência"],
                "observacao": linha["Observação"],
            }, carga_id=int(linha["ID"]))
            alteracoes += 1
        if alteracoes:
            st.success(f"{alteracoes} carga(s) atualizada(s).")
            st.rerun()
        else:
            st.info("Nada para salvar.")

    with col_excluir.expander("🗑️ Excluir uma carga (apaga também as notas dela)"):
        alvo = st.selectbox("ID da carga", visao["ID"].tolist())
        if st.button("Confirmar exclusão"):
            db.excluir_carga(int(alvo))
            st.success(f"Carga {alvo} excluída.")
            st.rerun()
