"""Cadastros por modalidade: municípios, transportadoras e veículos/embarcações."""

from __future__ import annotations

import streamlit as st

from src import db, ui
from src.config import (MODALIDADES, PRAZO_PADRAO_DIAS, TIPOS_TRANSPORTADORA,
                        UFS)

ui.configurar_pagina("Cadastros", "⚙️")

modalidade = ui.seletor_modalidade()
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
label_veiculo = info["veiculo_label"]
label_doc = info["doc_label"]

ui.cabecalho(f"⚙️ Cadastros — {info['label']}",
             "o que você cadastra aqui alimenta os menus das Entregas e as linhas do Cronograma")

aba_mun, aba_transp, aba_veic = st.tabs(
    ["📍 Municípios", "🏢 Transportadoras", f"{info['icone']} {label_veiculo}s"]
)

# ---------------------------------------------------------------------------
# Municípios
# ---------------------------------------------------------------------------
with aba_mun:
    with st.form("form_municipio", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        codigo = c1.text_input("Código")
        nome = c2.text_input("Município *")
        uf = c3.selectbox("UF", UFS)
        praca = c4.text_input("Praça / Eixo", value=info["label"])

        c5, c6, c7, c8 = st.columns(4)
        distancia = c5.number_input("Distância (km)", min_value=0.0, step=5.0)
        prazo = c6.number_input("Prazo (dias)", min_value=0, value=PRAZO_PADRAO_DIAS)
        freq = c7.number_input("Freq. semanal (viagens)", min_value=0, value=1)
        transp_padrao = c8.text_input("Transportadora padrão")

        if st.form_submit_button("Adicionar município", type="primary"):
            if not nome.strip():
                st.error("Informe o nome do município.")
            else:
                db.salvar_municipio({
                    "modalidade": modalidade, "codigo": codigo or None,
                    "nome": nome.strip(), "uf": uf, "praca": praca or None,
                    "distancia_km": float(distancia), "prazo_dias": int(prazo),
                    "freq_semanal": int(freq),
                    "transportadora_padrao": transp_padrao or None,
                    "ativo": True, "ordem": 50,
                })
                st.success(f"{nome} cadastrado.")
                st.rerun()

    df_mun = db.listar_municipios(modalidade)
    if df_mun.empty:
        st.info("Nenhum município cadastrado nesta modalidade.")
    else:
        editado = st.data_editor(
            df_mun[["id", "codigo", "nome", "uf", "praca", "distancia_km",
                    "prazo_dias", "freq_semanal", "transportadora_padrao",
                    "ativo", "ordem"]],
            width="stretch", hide_index=True, disabled=["id"],
            key="editor_municipios",
        )
        c_salvar, c_excluir = st.columns([1, 2])
        if c_salvar.button("💾 Salvar municípios", type="primary"):
            for _, linha in editado.iterrows():
                db.salvar_municipio({
                    "codigo": linha["codigo"], "nome": linha["nome"],
                    "uf": linha["uf"], "praca": linha["praca"],
                    "distancia_km": float(linha["distancia_km"] or 0),
                    "prazo_dias": int(linha["prazo_dias"] or PRAZO_PADRAO_DIAS),
                    "freq_semanal": int(linha["freq_semanal"] or 0),
                    "transportadora_padrao": linha["transportadora_padrao"],
                    "ativo": bool(linha["ativo"]), "ordem": int(linha["ordem"] or 0),
                }, municipio_id=int(linha["id"]))
            st.success("Cadastro atualizado.")
            st.rerun()
        with c_excluir.expander("🗑️ Excluir município"):
            alvo = st.selectbox("Município", df_mun["nome"].tolist(), key="del_mun")
            if st.button("Confirmar exclusão", key="btn_del_mun"):
                registro = df_mun[df_mun["nome"] == alvo].iloc[0]
                db.excluir_municipio(int(registro["id"]))
                st.success(f"{alvo} excluído.")
                st.rerun()

# ---------------------------------------------------------------------------
# Transportadoras
# ---------------------------------------------------------------------------
with aba_transp:
    with st.form("form_transportadora", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        nome_t = c1.text_input("Transportadora *")
        tipo = c2.selectbox("Tipo", TIPOS_TRANSPORTADORA)
        contato = c3.text_input("Contato")
        telefone = c4.text_input("Telefone")
        if st.form_submit_button("Adicionar transportadora", type="primary"):
            if not nome_t.strip():
                st.error("Informe o nome.")
            else:
                db.salvar_transportadora({
                    "modalidade": modalidade, "nome": nome_t.strip(),
                    "tipo": tipo, "contato": contato or None,
                    "telefone": telefone or None, "ativo": True,
                })
                st.success(f"{nome_t} cadastrada.")
                st.rerun()

    df_t = db.listar_transportadoras(modalidade)
    if df_t.empty:
        st.info("Nenhuma transportadora cadastrada.")
    else:
        st.dataframe(df_t[["id", "nome", "tipo", "contato", "telefone", "ativo"]],
                     width="stretch", hide_index=True)
        with st.expander("🗑️ Excluir transportadora"):
            alvo = st.selectbox("Transportadora", df_t["nome"].tolist(), key="del_t")
            if st.button("Confirmar exclusão", key="btn_del_t"):
                registro = df_t[df_t["nome"] == alvo].iloc[0]
                db.excluir_transportadora(int(registro["id"]))
                st.rerun()

# ---------------------------------------------------------------------------
# Veículos / embarcações
# ---------------------------------------------------------------------------
with aba_veic:
    with st.form("form_veiculo", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        descricao = c1.text_input(f"{label_veiculo} *")
        identificacao = c2.text_input(label_doc)
        motorista = c3.text_input("Motorista / responsável")
        c4, c5 = st.columns(2)
        telefone_v = c4.text_input("Telefone")
        transportadora_v = c5.text_input("Transportadora")
        if st.form_submit_button(f"Adicionar {label_veiculo.lower()}", type="primary"):
            if not descricao.strip():
                st.error(f"Informe o {label_veiculo.lower()}.")
            else:
                db.salvar_veiculo({
                    "modalidade": modalidade, "descricao": descricao.strip(),
                    "identificacao": identificacao or None,
                    "motorista": motorista or None, "telefone": telefone_v or None,
                    "transportadora": transportadora_v or None, "ativo": True,
                })
                st.success(f"{descricao} cadastrado.")
                st.rerun()

    df_v = db.listar_veiculos(modalidade)
    if df_v.empty:
        st.info(f"Nenhum(a) {label_veiculo.lower()} cadastrado(a).")
    else:
        st.dataframe(
            df_v[["id", "descricao", "identificacao", "motorista", "telefone",
                  "transportadora", "ativo"]],
            width="stretch", hide_index=True,
        )
        with st.expander(f"🗑️ Excluir {label_veiculo.lower()}"):
            alvo = st.selectbox(label_veiculo, df_v["descricao"].tolist(), key="del_v")
            if st.button("Confirmar exclusão", key="btn_del_v"):
                registro = df_v[df_v["descricao"] == alvo].iloc[0]
                db.excluir_veiculo(int(registro["id"]))
                st.rerun()
