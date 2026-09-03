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

# Marcadores da coluna "Situação" — apenas apresentação, o dado gravado
# continua sendo o código de status ("E", "P", "D"...).
MARCADOR_STATUS = {
    "P": "○ Pendente",
    "E": "● Entregue",
    "R": "◐ Reagendada",
    "D": "◆ Devolvida",
    "C": "× Cancelada",
}

ui.configurar_pagina("Checkout", "✅")

modalidade = ui.seletor_modalidade()
ui.rodape_sidebar()

info = MODALIDADES[modalidade]
label_placa = info["doc_label"]
ui.cabecalho(
    f'<span class="marca">◤</span> CENTRO DE CONTROLE DE ENTREGAS',
    f"{info['icone']} {info['label']}",
    "Checkout operacional por cliente",
)

cargas = db.listar_cargas(modalidade, com_checkout=False)
if cargas.empty:
    st.info("Nenhuma carga registrada nesta modalidade. Comece pela página "
            "**Importar Wynthor** para trazer as notas do carregamento.")
    st.stop()

datas = sorted(cargas["data_corte"].dropna().dt.date.unique(), reverse=True)
col_data, col_carga = st.columns([1, 2.4])
data_escolhida = col_data.selectbox("Data de corte", datas,
                                    format_func=lambda d: d.strftime("%d/%m/%Y"))

do_dia = cargas[cargas["data_corte"].dt.date == data_escolhida].set_index("id")
rotulo = {}
for identificador, linha in do_dia.iterrows():
    placa = linha["placa"] or f"sem {label_placa.lower()}"
    rotulo[identificador] = (f"{linha['municipio']} · {placa} · "
                             f"{STATUS.get(linha['status'], '')}")

carga_id = int(col_carga.selectbox("Carga em operação", list(rotulo.keys()),
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
entregues = int(notas["entregue"].sum())
com_ocorrencia = int(notas["com_ocorrencia"].sum())
conferidas = total - pendentes
pct = conferidas / total * 100 if total else 0.0

ui.chips([
    ("📅", "Corte", f"{data_escolhida:%d/%m/%Y}"),
    ("📍", "Destino", f"{carga['municipio']}/{carga['uf']}"),
    ("🚛", label_placa, carga["placa"] or "—"),
    ("📦", "Carregamento", carga["numcars"] or "—"),
    ("🏁", "Status", STATUS.get(carga["status"], "—")),
])

ui.kpis([
    {"icone": "🧾", "rotulo": "Notas fiscais", "valor": total,
     "detalhe": "no carregamento"},
    {"icone": "🏢", "rotulo": "Clientes", "valor": int(notas["codcli"].nunique()),
     "detalhe": "pontos de entrega"},
    {"icone": "✅", "rotulo": "Entregues", "valor": entregues,
     "tom": "bom" if entregues else None,
     "detalhe": f"{entregues / total * 100:.0f}% do total" if total else ""},
    {"icone": "⏳", "rotulo": "Pendentes", "valor": pendentes,
     "tom": "atencao" if pendentes else "bom",
     "detalhe": "aguardando baixa" if pendentes else "nada em aberto"},
    {"icone": "⚠️", "rotulo": "Ocorrências", "valor": com_ocorrencia,
     "tom": "atencao" if com_ocorrencia else None,
     "detalhe": "notas com problema"},
    {"icone": "📊", "rotulo": "Checkout", "valor": f"{pct:.0f}", "unidade": "%",
     "tom": "bom" if pct >= 100 else "destaque",
     "detalhe": f"{conferidas} de {total} conferidas"},
])

ui.progresso(conferidas, total,
             f"{conferidas} de {total} notas conferidas",
             "carga fechada" if pendentes == 0 else f"{pendentes} em aberto")

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
        "Situação": (MARCADOR_STATUS.get(status_unicos[0], "○ Pendente")
                     if len(status_unicos) == 1 else "◈ Parcial"),
        "Observação": observacoes[0] if len(observacoes) == 1 else "",
    })

tabela = pd.DataFrame(linhas).sort_values("Cliente").reset_index(drop=True)

# ---------------------------------------------------------------------------
# Busca e filtro
# ---------------------------------------------------------------------------
ui.secao("Área de trabalho", "conferência nota a nota, agrupada por cliente")

col_f1, col_f2 = st.columns([3, 1])
busca = col_f1.text_input(
    "Buscar", placeholder="🔍  nota fiscal, cliente ou código — ex.: 450055")
filtro = col_f2.selectbox("Filtro", ["Todos", "Só pendentes", "Só com ocorrência"])

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

ui.secao(f"{len(visivel)} clientes em conferência",
         "as marcações ficam no navegador e só vão ao servidor ao gravar")

visivel = visivel.reset_index(drop=True)

# A chave do editor carrega uma versão: depois de gravar, ela muda e o widget
# volta limpo, sem reaplicar a mesma edição no rerun seguinte.
chave_versao = f"versao_editor_{carga_id}"
versao = st.session_state.setdefault(chave_versao, 0)
chave_editor = f"editor_clientes_{carga_id}_{versao}"


def _coletar_edicoes() -> dict[str, dict]:
    """Lê o que foi mexido na tabela, sem tocar no banco."""
    estado = st.session_state.get(chave_editor, {})
    resultado = {}
    for posicao, campos in estado.get("edited_rows", {}).items():
        linha = visivel.iloc[int(posicao)]
        ocorrencia = campos.get("Ocorrência", linha["Ocorrência"])
        if ocorrencia == MISTO:
            ocorrencia = "Sem ocorrência"
        resultado[linha["Cód."]] = {
            "marcado": bool(campos.get("✔", linha["✔"])),
            "ocorrencia": ocorrencia,
            "observacao": campos.get("Observação", linha["Observação"]),
        }
    return resultado


def _gravar(restante_entregue: bool = False) -> None:
    """Grava tudo de uma vez: as linhas mexidas e, opcionalmente, o restante."""
    edicoes = _coletar_edicoes()
    momento = agora()
    alterados = 0
    tratados = set()

    for codigo, dados in edicoes.items():
        if dados["marcado"]:
            novo_status = "E"                       # entregue
        elif dados["ocorrencia"] != "Sem ocorrência":
            novo_status = "D"                       # não entregue, com ocorrência
        else:
            novo_status = "P"                       # segue pendente

        ids = notas.loc[notas["codcli"].astype(str) == codigo, "id"].tolist()
        alterados += db.checkout_notas(ids, novo_status, dados["ocorrencia"],
                                       observacao=dados["observacao"] or None,
                                       momento=momento)
        tratados.add(codigo)

    if restante_entregue:
        restantes = [c for c in visivel["Cód."] if c not in tratados]
        ids = notas.loc[notas["codcli"].astype(str).isin(restantes)
                        & notas["pendente"], "id"].tolist()
        alterados += db.checkout_notas(ids, "E", "Sem ocorrência", momento=momento)

    if alterados:
        db.recalcular_status_carga(carga_id)
        st.session_state[chave_versao] = versao + 1
        st.session_state["ultimo_checkout"] = (
            f"{alterados} nota(s) gravada(s) às {momento:%H:%M} de "
            f"{momento:%d/%m/%Y}.")


aviso = st.session_state.pop("ultimo_checkout", None)
if aviso:
    st.success(aviso)

# O formulário é o que elimina a espera: dentro dele o Streamlit NÃO recarrega
# a página a cada caixa marcada. Você marca 40 clientes de graça e só o botão
# de gravar conversa com o servidor — uma ida, não quarenta.
with st.form(f"form_checkout_{carga_id}", border=False):
    st.data_editor(
        visivel, width="stretch", hide_index=True, num_rows="fixed",
        # altura acompanha a quantidade de clientes, com teto para não empurrar
        # os botões para fora da tela
        height=min(120 + 35 * len(visivel), 620),
        key=chave_editor,
        disabled=["Cód.", "Cliente", "NFs", "Notas fiscais", "Checkout", "Situação"],
        column_config={
            "✔": st.column_config.CheckboxColumn(
                "✓", width="small", help="marque quem recebeu"),
            "Cód.": st.column_config.TextColumn("CÓD.", width="small"),
            "Cliente": st.column_config.TextColumn("CLIENTE", width="large"),
            "NFs": st.column_config.NumberColumn(
                "NF", width="small", help="quantidade de notas do cliente"),
            "Notas fiscais": st.column_config.TextColumn(
                "NOTAS FISCAIS", width="medium"),
            "Ocorrência": st.column_config.SelectboxColumn(
                "OCORRÊNCIA", options=OCORRENCIAS + [MISTO], width="medium"),
            "Checkout": st.column_config.DatetimeColumn(
                "CHECKOUT", format="DD/MM  HH:mm", width="small",
                help="data e hora gravadas automaticamente"),
            "Situação": st.column_config.TextColumn("SITUAÇÃO", width="small"),
            "Observação": st.column_config.TextColumn("OBSERVAÇÃO", width="medium"),
        },
    )

    col_g1, col_g2 = st.columns(2)
    gravar = col_g1.form_submit_button("💾 Gravar marcações", type="primary",
                                       width="stretch")
    gravar_excecao = col_g2.form_submit_button(
        "⚡ Gravar e dar o restante como entregue", width="stretch",
        help="Registra só as exceções que você marcou e considera todo o resto "
             "da lista como entregue — o caminho mais rápido quando a carga "
             "saiu quase toda certa.")

if gravar or gravar_excecao:
    _gravar(restante_entregue=gravar_excecao)
    st.rerun()

st.caption("Fluxo rápido: filtre **Só pendentes**, registre as ocorrências dos "
           "clientes que deram problema e use o botão da direita — a carga "
           "inteira fecha numa única gravação.")

col_limpar, _ = st.columns([1, 3])
if col_limpar.button("↩️ Voltar visíveis para pendente"):
    ids = notas.loc[notas["codcli"].astype(str).isin(visivel["Cód."]), "id"].tolist()
    db.checkout_notas(ids, "P", "Sem ocorrência")
    db.recalcular_status_carga(carga_id)
    st.session_state[chave_versao] = versao + 1
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
