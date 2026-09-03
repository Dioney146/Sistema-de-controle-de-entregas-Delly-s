"""Camada visual do sistema — Centro de Controle Logístico.

Aqui ficam o CSS e os componentes de apresentação. Nada nesta camada altera
dados, cálculos ou regras: ela só decide como as informações aparecem.
"""

from __future__ import annotations

import html
from datetime import date

import streamlit as st

from src import db
from src.config import (APP_NAME, MESES, MODALIDADE_PADRAO, MODALIDADES,
                        modalidade_label)

CSS = """
<style>
    :root {
        --fundo:        #0B0D10;
        --superficie:   #14181D;
        --superficie-2: #1B2027;
        --linha:        #252B33;
        --texto:        #E8EAED;
        --texto-fraco:  #8A939F;
        --laranja:      #FF6B1A;
        --verde:        #3FB950;
        --ambar:        #D29922;
        --vermelho:     #E5534B;
    }

    .block-container {
        padding-top: 1.6rem;
        padding-bottom: 4rem;
        max-width: 1600px;
    }

    /* ---------- cabecalho operacional ---------- */
    .oc-topo {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 0.5rem 1.1rem;
        padding-bottom: 0.85rem;
        margin-bottom: 1.05rem;
        border-bottom: 1px solid var(--linha);
    }
    .oc-topo h1 {
        font-size: 1.26rem;
        font-weight: 700;
        letter-spacing: -0.015em;
        margin: 0;
        line-height: 1.2;
    }
    .oc-topo h1 .marca { color: var(--laranja); }
    .oc-topo .oc-sub { font-size: 0.82rem; color: var(--texto-fraco); margin: 0; }
    .oc-topo .oc-espaco { flex: 1 1 auto; }

    /* ---------- chips de contexto ---------- */
    .oc-chips {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin: -0.2rem 0 1.05rem;
    }
    .oc-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: var(--superficie);
        border: 1px solid var(--linha);
        border-radius: 999px;
        padding: 0.22rem 0.7rem;
        font-size: 0.76rem;
        color: var(--texto-fraco);
        white-space: nowrap;
    }
    .oc-chip b { color: var(--texto); font-weight: 600; }
    .oc-chip .ico { opacity: 0.7; font-size: 0.85em; }

    /* ---------- grade de KPIs ---------- */
    .oc-kpis {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
        gap: 0.6rem;
        margin-bottom: 1.05rem;
    }
    .oc-kpi {
        background: var(--superficie);
        border: 1px solid var(--linha);
        border-radius: 10px;
        padding: 0.72rem 0.9rem 0.8rem;
        position: relative;
        overflow: hidden;
        min-width: 0;
    }
    .oc-kpi::before {
        content: "";
        position: absolute;
        left: 0; top: 0; bottom: 0;
        width: 2px;
        background: var(--linha);
    }
    .oc-kpi.destaque::before { background: var(--laranja); }
    .oc-kpi.bom::before      { background: var(--verde); }
    .oc-kpi.atencao::before  { background: var(--ambar); }

    .oc-kpi .rotulo {
        display: flex;
        align-items: center;
        gap: 0.32rem;
        font-size: 0.68rem;
        font-weight: 600;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        color: var(--texto-fraco);
        margin-bottom: 0.25rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .oc-kpi .valor {
        font-size: clamp(1.55rem, 2.4vw, 2.15rem);
        font-weight: 700;
        line-height: 1.05;
        letter-spacing: -0.03em;
        font-variant-numeric: tabular-nums;
        color: var(--texto);
        word-break: break-word;
    }
    .oc-kpi.destaque .valor { color: var(--laranja); }
    .oc-kpi.bom .valor      { color: var(--verde); }
    .oc-kpi.atencao .valor  { color: var(--ambar); }
    .oc-kpi .valor .unidade {
        font-size: 0.5em;
        font-weight: 600;
        color: var(--texto-fraco);
        margin-left: 0.12em;
        letter-spacing: 0;
    }
    .oc-kpi .detalhe {
        font-size: 0.72rem;
        color: var(--texto-fraco);
        margin-top: 0.2rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* ---------- barra de progresso ---------- */
    .oc-progresso { margin: 0 0 1.25rem; }
    .oc-progresso .trilho {
        height: 6px;
        width: 100%;
        background: var(--superficie-2);
        border-radius: 999px;
        overflow: hidden;
    }
    .oc-progresso .preenchido {
        height: 100%;
        background: linear-gradient(90deg, var(--laranja), #FFA05C);
        border-radius: 999px;
        transition: width 0.35s ease;
    }
    .oc-progresso .preenchido.completo {
        background: linear-gradient(90deg, var(--verde), #6FD47E);
    }
    .oc-progresso .legenda {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        font-size: 0.72rem;
        color: var(--texto-fraco);
        margin-top: 0.35rem;
    }
    .oc-progresso .legenda b { color: var(--texto); font-weight: 600; }

    /* ---------- secoes ---------- */
    .oc-secao {
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 0.55rem;
        margin: 0.3rem 0 0.5rem;
    }
    .oc-secao .titulo {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.11em;
        text-transform: uppercase;
        color: var(--texto-fraco);
    }
    .oc-secao .nota { font-size: 0.78rem; color: var(--texto-fraco); }

    /* ---------- tabela ---------- */
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
        border: 1px solid var(--linha);
        border-radius: 10px;
        overflow: hidden;
    }

    /* ---------- controles ---------- */
    div[data-testid="stTextInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-baseweb="select"] > div {
        background: var(--superficie) !important;
        border-color: var(--linha) !important;
        font-size: 0.86rem;
    }
    label[data-testid="stWidgetLabel"] p {
        font-size: 0.72rem !important;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--texto-fraco) !important;
    }
    div[data-testid="stForm"] { border: none; padding: 0; }
    button[kind="secondary"] {
        border-color: var(--linha) !important;
        background: var(--superficie) !important;
    }
    div[data-testid="stExpander"] details {
        border: 1px solid var(--linha);
        border-radius: 10px;
        background: var(--superficie);
    }
    div[data-testid="stExpander"] summary { font-size: 0.85rem; }
    hr { border-color: var(--linha) !important; margin: 1.35rem 0 !important; }

    section[data-testid="stSidebar"] { background: var(--superficie); }
    section[data-testid="stSidebar"] hr { margin: 0.9rem 0 !important; }

    /* ---------- telas estreitas ---------- */
    @media (max-width: 640px) {
        .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
        .oc-kpis { grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); }
        .oc-kpi { padding: 0.6rem 0.7rem; }
        .oc-kpi .valor { font-size: 1.45rem; }
    }
</style>
"""


def configurar_pagina(titulo: str, icone: str = "🚚") -> None:
    st.set_page_config(page_title=f"{titulo} · Delly's", page_icon=icone,
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)

    # o preparo do banco roda uma única vez por processo
    if db.preparar():
        st.error(
            "O banco ainda está no formato antigo (carga por NUMCAR). "
            "Rode o SQL de migração descrito no README (DROP TABLE cargas) "
            "para o app criar a nova estrutura com notas fiscais."
        )
        st.stop()


# ---------------------------------------------------------------------------
# Componentes visuais
# ---------------------------------------------------------------------------
def cabecalho(titulo: str, subtitulo: str = "", contexto: str = "") -> None:
    """Cabeçalho compacto: título à esquerda, contexto operacional à direita."""
    direita = f'<div class="oc-sub">{html.escape(contexto)}</div>' if contexto else ""
    st.markdown(
        f'<div class="oc-topo">'
        f'<h1>{titulo}</h1>'
        f'<div class="oc-sub">{html.escape(subtitulo)}</div>'
        f'<div class="oc-espaco"></div>{direita}'
        f'</div>',
        unsafe_allow_html=True,
    )


def chips(itens: list[tuple[str, str, str]]) -> None:
    """Linha de contexto: lista de (ícone, rótulo, valor)."""
    partes = [
        f'<span class="oc-chip"><span class="ico">{icone}</span>'
        f'{html.escape(rotulo)} <b>{html.escape(str(valor))}</b></span>'
        for icone, rotulo, valor in itens
    ]
    st.markdown(f'<div class="oc-chips">{"".join(partes)}</div>',
                unsafe_allow_html=True)


def kpis(itens: list[dict]) -> None:
    """Grade de KPIs que se ajusta à quantidade de cartões e à largura da tela.

    Cada item: {"icone", "rotulo", "valor", "unidade"?, "detalhe"?, "tom"?}
    tom: "destaque" (laranja), "bom" (verde), "atencao" (âmbar) ou nada.
    """
    cartoes = []
    for item in itens:
        tom = item.get("tom") or ""
        unidade = (f'<span class="unidade">{html.escape(item["unidade"])}</span>'
                   if item.get("unidade") else "")
        detalhe = (f'<div class="detalhe">{html.escape(item["detalhe"])}</div>'
                   if item.get("detalhe") else "")
        cartoes.append(
            f'<div class="oc-kpi {tom}">'
            f'<div class="rotulo"><span>{item.get("icone", "")}</span>'
            f'{html.escape(item["rotulo"])}</div>'
            f'<div class="valor">{html.escape(str(item["valor"]))}{unidade}</div>'
            f'{detalhe}</div>'
        )
    st.markdown(f'<div class="oc-kpis">{"".join(cartoes)}</div>',
                unsafe_allow_html=True)


def progresso(feitos: int, total: int, rotulo_esq: str = "",
              rotulo_dir: str = "") -> None:
    """Barra de progresso integrada, com legenda nas pontas."""
    pct = (feitos / total * 100) if total else 0.0
    completo = " completo" if total and feitos >= total else ""
    st.markdown(
        f'<div class="oc-progresso">'
        f'<div class="trilho"><div class="preenchido{completo}" '
        f'style="width:{pct:.1f}%"></div></div>'
        f'<div class="legenda"><span>{html.escape(rotulo_esq)}</span>'
        f'<span>{html.escape(rotulo_dir)}</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def secao(titulo: str, nota: str = "") -> None:
    complemento = f'<span class="nota">{html.escape(nota)}</span>' if nota else ""
    st.markdown(
        f'<div class="oc-secao"><span class="titulo">{html.escape(titulo)}</span>'
        f'{complemento}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
def seletor_modalidade() -> str:
    if "modalidade" not in st.session_state:
        st.session_state["modalidade"] = MODALIDADE_PADRAO

    codigos = list(MODALIDADES.keys())
    indice = codigos.index(st.session_state["modalidade"])
    escolha = st.sidebar.radio("Modalidade", codigos, index=indice,
                               format_func=modalidade_label,
                               key="seletor_modalidade")
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

    with st.sidebar.expander("⏱️ Velocidade do banco"):
        st.caption("Mede o tempo de ida e volta até o banco. Cada clique do "
                   "checkout custa cerca de 4 dessas viagens.")
        if st.button("Medir agora", key="btn_latencia"):
            st.session_state["latencia"] = db.medir_latencia()
        medida = st.session_state.get("latencia")
        if medida:
            st.metric("Por consulta", f"{medida['mediana_ms']:.0f} ms")
            st.caption(
                f"média {medida['media_ms']:.0f} ms · pior {medida['pior_ms']:.0f} ms\n\n"
                f"≈ **{medida['por_clique_ms']:.0f} ms** por clique só de rede"
            )


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------
def formatar_reais(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_numero(valor: float, casas: int = 0) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def label_veiculo(modalidade: str) -> str:
    return MODALIDADES[modalidade]["veiculo_label"]
