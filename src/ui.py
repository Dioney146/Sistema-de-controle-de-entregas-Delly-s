"""Componentes de interface reaproveitados pelas páginas do Streamlit."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src import db
from src.config import (APP_NAME, MESES, MODALIDADE_PADRAO, MODALIDADES,
                        modalidade_label)

CSS = """
<style>
    .block-container {padding-top: 2.2rem; padding-bottom: 3rem;}
    div[data-testid="stMetricValue"] {font-size: 1.7rem;}
    div[data-testid="stMetric"] {
        background: rgba(128,128,128,0.07);
        border: 1px solid rgba(128,128,128,0.18);
        border-radius: 10px;
        padding: 0.8rem 1rem;
    }
    .cabecalho {
        border-left: 5px solid #E4572E;
        padding-left: 0.9rem;
        margin-bottom: 1.2rem;
    }
    .cabecalho h1 {margin: 0; font-size: 1.6rem;}
    .cabecalho p {margin: 0.2rem 0 0; opacity: 0.75; font-size: 0.9rem;}
</style>
"""


def configurar_pagina(titulo: str, icone: str = "🚚") -> None:
    st.set_page_config(page_title=f"{titulo} · Delly's", page_icon=icone,
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)
    if db.esquema_desatualizado():
        st.error(
            "O banco ainda está no formato antigo (carga por NUMCAR). "
            "Rode o SQL de migração descrito no README (DROP TABLE cargas) "
            "para o app criar a nova estrutura com notas fiscais."
        )
        st.stop()
    db.init_db()
    db.semear_dados_iniciais()


def cabecalho(titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f'<div class="cabecalho"><h1>{titulo}</h1><p>{subtitulo}</p></div>',
        unsafe_allow_html=True,
    )


def seletor_modalidade() -> str:
    """Seletor de modalidade na sidebar, persistido em session_state."""
    if "modalidade" not in st.session_state:
        st.session_state["modalidade"] = MODALIDADE_PADRAO

    codigos = list(MODALIDADES.keys())
    indice = codigos.index(st.session_state["modalidade"])
    escolha = st.sidebar.radio(
        "Modalidade", codigos, index=indice,
        format_func=modalidade_label, key="seletor_modalidade",
    )
    st.session_state["modalidade"] = escolha
    st.sidebar.caption(MODALIDADES[escolha]["descricao"])
    return escolha


def seletor_periodo(modalidade: str, com_mes: bool = True) -> tuple[int, int | None]:
    hoje = date.today()
    anos = db.anos_disponiveis(modalidade)
    ano_padrao = hoje.year if hoje.year in anos else anos[-1]

    ano = st.sidebar.selectbox("Ano", anos, index=anos.index(ano_padrao))
    if not com_mes:
        return ano, None
    mes_nome = st.sidebar.selectbox("Mês", MESES, index=hoje.month - 1)
    return ano, MESES.index(mes_nome) + 1


def rodape_sidebar() -> None:
    st.sidebar.divider()
    destino = "SQLite (local)" if db.is_sqlite() else "Postgres"
    st.sidebar.caption(f"{APP_NAME}\n\nBanco: **{destino}**")


def formatar_reais(valor: float) -> str:
    return (f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))


def formatar_numero(valor: float, casas: int = 0) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def label_veiculo(modalidade: str) -> str:
    return MODALIDADES[modalidade]["veiculo_label"]
