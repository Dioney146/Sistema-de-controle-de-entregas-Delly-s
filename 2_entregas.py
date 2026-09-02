"""Lançamento, edição e baixa das cargas."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src import db, ui
from src.config import (MODALIDADES, OCORRENCIAS, PRAZO_PADRAO_DIAS, STATUS,
                        UFS)

ui.configurar_pagina("Entregas", "🧾")

modalidade = ui.seletor_modalidade()
ano, mes = ui.seletor_periodo(modalidade)
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
label_veiculo = info["veiculo_label"]
ui.cabecalho(f"{info['icone']} Entregas — {info['label']}",
             "cadastro de cargas, baixa de entrega e registro de ocorrências")

cadastro_mun = db.listar_municipios(modalidade)
municipios = cadastro_mun["nome"].tolist() if not cadastro_mun.empty else []
prazos = (dict(zip(cadastro_mun["nome"], cadastro_mun["prazo_dias"]))
          if not cadastro_mun.empty else {})
transportadoras = db.listar_transportadoras(modalidade)
lista_transp = transportadoras["nome"].tolist() if not transportadoras.empty else []
veiculos = db.listar_veiculos(modalidade)
lista_veic = veiculos["identificacao"].dropna().tolist() if not veiculos.empty else []
lista_motoristas = veiculos["motorista"].dropna().tolist() if not veiculos.empty else []

aba_nova, aba_lista = st.tabs(["➕ Nova carga", "📋 Cargas lançadas"])

# ---------------------------------------------------------------------------
# Nova carga
# ---------------------------------------------------------------------------
with aba_nova:
    with st.form("form_nova_carga", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        numcar = c1.text_input("Carregamento (NUMCAR)")
        data_saida = c2.date_input("Data de saída / corte", value=date.today(),
                                   format="DD/MM/YYYY")
        municipio = c3.selectbox("Município", municipios + ["— outro —"]) if municipios \
            else st.text_input("Município")
        if municipio == "— outro —":
            municipio = st.text_input("Digite o município")

        c4, c5, c6 = st.columns(3)
        uf = c4.selectbox("UF", UFS, index=0)
        transportadora = c5.selectbox("Transportadora", ["—"] + lista_transp)
        motorista = c6.selectbox("Motorista / responsável",
                                 ["—"] + sorted(set(lista_motoristas))) \
            if lista_motoristas else c6.text_input("Motorista / responsável")

        c7, c8, c9 = st.columns(3)
        veiculo = c7.selectbox(label_veiculo, ["—"] + lista_veic) if lista_veic \
            else c7.text_input(label_veiculo)
        pedidos = c8.number_input("Pedidos / notas", min_value=0, step=1)
        peso_kg = c9.number_input("Peso (kg)", min_value=0.0, step=1.0, format="%.3f")

        c10, c11, c12 = st.columns(3)
        valor = c10.number_input("Valor (R$)", min_value=0.0, step=100.0, format="%.2f")
        prazo = int(prazos.get(municipio, PRAZO_PADRAO_DIAS) or PRAZO_PADRAO_DIAS)
        previsao = c11.date_input("Previsão de entrega",
                                  value=data_saida + timedelta(days=prazo),
                                  format="DD/MM/YYYY")
        status = c12.selectbox("Status", list(STATUS.keys()),
                               format_func=lambda k: f"{k} · {STATUS[k]}")

        c13, c14 = st.columns([1, 2])
        ocorrencia = c13.selectbox("Ocorrência", OCORRENCIAS)
        observacao = c14.text_input("Observação")

        if st.form_submit_button("Salvar carga", type="primary"):
            if not municipio:
                st.error("Informe o município.")
            else:
                db.salvar_carga({
                    "modalidade": modalidade,
                    "numcar": numcar.strip() or None,
                    "data_saida": data_saida,
                    "municipio": municipio,
                    "uf": uf,
                    "praca": None,
                    "transportadora": None if transportadora == "—" else transportadora,
                    "motorista": None if motorista == "—" else motorista,
                    "veiculo": None if veiculo == "—" else veiculo,
                    "pedidos": int(pedidos),
                    "clientes": 0,
                    "peso_kg": float(peso_kg),
                    "valor": float(valor),
                    "previsao_entrega": previsao,
                    "data_entrega": None,
                    "status": status,
                    "ocorrencia": ocorrencia,
                    "observacao": observacao or None,
                    "distancia_km": 0.0,
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

    filtro_status = st.multiselect(
        "Filtrar por status", list(STATUS.keys()),
        format_func=lambda k: STATUS[k], default=[],
    )
    if filtro_status:
        df = df[df["status"].isin(filtro_status)]

    visao = df[["id", "numcar", "data_saida", "municipio", "uf", "transportadora",
                "motorista", "veiculo", "pedidos", "peso_kg", "valor",
                "previsao_entrega", "data_entrega", "status", "ocorrencia",
                "dias_atraso", "observacao"]].copy()
    visao = visao.rename(columns={
        "id": "ID", "numcar": "Carregamento", "data_saida": "Saída",
        "municipio": "Município", "uf": "UF", "transportadora": "Transportadora",
        "motorista": "Motorista", "veiculo": label_veiculo, "pedidos": "Pedidos",
        "peso_kg": "Peso (kg)", "valor": "Valor (R$)",
        "previsao_entrega": "Previsão", "data_entrega": "Entrega",
        "status": "Status", "ocorrencia": "Ocorrência",
        "dias_atraso": "Dias atraso", "observacao": "Observação",
    })

    editado = st.data_editor(
        visao, width="stretch", hide_index=True, num_rows="fixed",
        disabled=["ID", "Carregamento", "Dias atraso"],
        column_config={
            "Saída": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Previsão": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Entrega": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Status": st.column_config.SelectboxColumn(options=list(STATUS.keys())),
            "Ocorrência": st.column_config.SelectboxColumn(options=OCORRENCIAS),
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
                "data_saida": linha["Saída"],
                "municipio": linha["Município"],
                "uf": linha["UF"],
                "transportadora": linha["Transportadora"],
                "motorista": linha["Motorista"],
                "veiculo": linha[label_veiculo],
                "pedidos": int(linha["Pedidos"] or 0),
                "peso_kg": float(linha["Peso (kg)"] or 0),
                "valor": float(linha["Valor (R$)"] or 0),
                "previsao_entrega": linha["Previsão"],
                "data_entrega": linha["Entrega"],
                "status": linha["Status"],
                "ocorrencia": linha["Ocorrência"],
                "observacao": linha["Observação"],
            }, carga_id=int(linha["ID"]))
            alteracoes += 1
        st.success(f"{alteracoes} carga(s) atualizada(s).") if alteracoes \
            else st.info("Nada para salvar.")
        st.rerun()

    with col_excluir.expander("🗑️ Excluir uma carga"):
        alvo = st.selectbox("ID da carga", visao["ID"].tolist())
        if st.button("Confirmar exclusão"):
            db.excluir_carga(int(alvo))
            st.success(f"Carga {alvo} excluída.")
            st.rerun()
