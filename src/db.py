"""Camada de banco de dados.

Funciona em dois modos, sem mudar o código:

* **Local** — SQLite em `data/dellys_entregas.db`
* **Streamlit Cloud** — Postgres (Supabase) via `st.secrets["database"]["url"]`

Modelo de dados
---------------
A **carga** é identificada por  modalidade + data de corte + município + placa.
Uma mesma placa pode levar mais de um carregamento (NUMCAR) na mesma viagem;
todos os NUMCAR da viagem ficam guardados na coluna `numcars`.

Cada carga tem N **notas fiscais** (tabela `notas`), e é nelas que acontece o
checkout: cada nota recebe status (entregue, devolvida, reagendada...) e
ocorrência. O status da carga é recalculado a partir das notas.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, MetaData,
    String, Table, UniqueConstraint, func,
)

from src.config import (MODALIDADE_PADRAO, PRAZO_PADRAO_DIAS,
                        STATUS_NOTA_RESOLVIDO, agora)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
SQLITE_URL = f"sqlite:///{DATA_DIR / 'dellys_entregas.db'}"

metadata = MetaData()

municipios = Table(
    "municipios", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("modalidade", String(20), nullable=False),
    Column("codigo", String(20)),
    Column("nome", String(120), nullable=False),
    Column("uf", String(2), default="AM"),
    Column("praca", String(60)),
    Column("distancia_km", Float, default=0.0),
    Column("prazo_dias", Integer, default=PRAZO_PADRAO_DIAS),
    Column("freq_semanal", Integer, default=1),
    Column("transportadora_padrao", String(80)),
    Column("ativo", Boolean, default=True),
    Column("ordem", Integer, default=0),
    UniqueConstraint("modalidade", "nome", name="uq_municipio_modalidade"),
)

transportadoras = Table(
    "transportadoras", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("modalidade", String(20), nullable=False),
    Column("nome", String(80), nullable=False),
    Column("tipo", String(20), default="Terceiro"),
    Column("contato", String(80)),
    Column("telefone", String(30)),
    Column("ativo", Boolean, default=True),
    UniqueConstraint("modalidade", "nome", name="uq_transp_modalidade"),
)

veiculos = Table(
    "veiculos", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("modalidade", String(20), nullable=False),
    Column("descricao", String(80), nullable=False),
    Column("identificacao", String(30)),
    Column("motorista", String(80)),
    Column("telefone", String(30)),
    Column("transportadora", String(80)),
    Column("ativo", Boolean, default=True),
    UniqueConstraint("modalidade", "descricao", "identificacao",
                     name="uq_veiculo_modalidade"),
)

# A chave da carga: modalidade + data de corte + município + placa
cargas = Table(
    "cargas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("modalidade", String(20), nullable=False),
    Column("data_corte", Date, nullable=False),
    Column("municipio", String(120), nullable=False),
    Column("placa", String(30), nullable=False, default=""),
    Column("uf", String(2), default="AM"),
    Column("numcars", String(200)),        # carregamentos da viagem, separados por vírgula
    Column("praca", String(60)),
    Column("transportadora", String(80)),
    Column("motorista", String(80)),
    Column("data_saida_origem", Date),     # DTSAIDA do Wynthor (informativo)
    Column("previsao_entrega", Date),
    Column("data_entrega", Date),
    Column("status", String(1), default="P"),
    Column("ocorrencia", String(60), default="Sem ocorrência"),
    Column("observacao", String(400)),
    Column("peso_kg", Float, default=0.0),
    Column("valor", Float, default=0.0),
    Column("distancia_km", Float, default=0.0),
    Column("origem_dado", String(20), default="manual"),
    Column("criado_em", DateTime, server_default=func.now()),
    UniqueConstraint("modalidade", "data_corte", "municipio", "placa",
                     name="uq_carga_chave"),
)

notas = Table(
    "notas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("carga_id", Integer, ForeignKey("cargas.id", ondelete="CASCADE"),
           nullable=False),
    Column("modalidade", String(20), nullable=False),
    Column("numcar", String(30)),
    Column("numnota", String(30), nullable=False),
    Column("codcli", String(30)),
    Column("cliente", String(200)),
    Column("status", String(1), default="P"),
    Column("ocorrencia", String(60), default="Sem ocorrência"),
    Column("data_checkout", Date),
    Column("checkout_em", DateTime),      # data e hora exatas do checkout
    Column("observacao", String(300)),
    UniqueConstraint("carga_id", "numcar", "numnota", name="uq_nota_carga"),
)


def get_database_url() -> str:
    """URL do banco: secrets do Streamlit > variável de ambiente > SQLite."""
    try:
        import streamlit as st

        if "database" in st.secrets and st.secrets["database"].get("url"):
            return st.secrets["database"]["url"]
    except Exception:
        pass
    return os.environ.get("DATABASE_URL", SQLITE_URL)


def _build_engine() -> sa.Engine:
    url = get_database_url()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("sqlite"):
        return sa.create_engine(url, connect_args={"check_same_thread": False})
    # sem pool_pre_ping: ele dispara um "SELECT 1" antes de cada consulta, o que
    # dobra as viagens de rede até o Supabase. pool_recycle evita conexão morta.
    return sa.create_engine(url, pool_recycle=1800, pool_size=5, max_overflow=5)


try:
    import streamlit as st

    @st.cache_resource(show_spinner=False)
    def get_engine() -> sa.Engine:
        return _build_engine()
except Exception:
    _ENGINE: sa.Engine | None = None

    def get_engine() -> sa.Engine:  # type: ignore[misc]
        global _ENGINE
        if _ENGINE is None:
            _ENGINE = _build_engine()
        return _ENGINE


def init_db() -> None:
    metadata.create_all(get_engine())
    _garantir_colunas()


def _preparar_banco() -> bool:
    """Verifica esquema, cria tabelas e semeia dados. Devolve True se o esquema
    ainda é o antigo. Chamado uma única vez por processo (ver `preparar`)."""
    if esquema_desatualizado():
        return True
    init_db()
    semear_dados_iniciais()
    return False


try:
    import streamlit as _st

    @_st.cache_resource(show_spinner=False)
    def preparar() -> bool:
        return _preparar_banco()
except Exception:
    _PREPARADO: bool | None = None

    def preparar() -> bool:  # type: ignore[misc]
        global _PREPARADO
        if _PREPARADO is None:
            _PREPARADO = _preparar_banco()
        return _PREPARADO


def _garantir_colunas() -> None:
    """Adiciona colunas que surgiram depois que o banco já existia.

    `create_all` só cria tabelas novas, não altera as existentes — então as
    colunas acrescentadas em versões posteriores entram por aqui.
    """
    novas = {
        "notas": {"checkout_em": "TIMESTAMP"},
    }
    inspetor = sa.inspect(get_engine())
    for tabela, colunas in novas.items():
        if tabela not in inspetor.get_table_names():
            continue
        existentes = {c["name"] for c in inspetor.get_columns(tabela)}
        for coluna, tipo in colunas.items():
            if coluna in existentes:
                continue
            with get_engine().begin() as conn:
                conn.execute(sa.text(
                    f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}"))


def is_sqlite() -> bool:
    return get_engine().dialect.name == "sqlite"


def medir_latencia(repeticoes: int = 7) -> dict:
    """Tempo de ida e volta até o banco, em milissegundos.

    Serve para comparar regiões do Supabase: cada clique do checkout custa
    cerca de 4 dessas viagens.
    """
    import time

    tempos = []
    with get_engine().connect() as conn:
        conn.execute(sa.text("SELECT 1"))  # descarta a 1a (abre a conexão)
        for _ in range(repeticoes):
            inicio = time.perf_counter()
            conn.execute(sa.text("SELECT 1"))
            tempos.append((time.perf_counter() - inicio) * 1000)
    tempos.sort()
    return {
        "media_ms": round(sum(tempos) / len(tempos), 1),
        "mediana_ms": round(tempos[len(tempos) // 2], 1),
        "pior_ms": round(tempos[-1], 1),
        "por_clique_ms": round(sum(tempos) / len(tempos) * 4, 0),
    }


def esquema_desatualizado() -> bool:
    """True se a tabela `cargas` ainda for a versão antiga (com `numcar`)."""
    try:
        inspetor = sa.inspect(get_engine())
        if "cargas" not in inspetor.get_table_names():
            return False
        colunas = {c["name"] for c in inspetor.get_columns("cargas")}
        return "data_corte" not in colunas
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _read(stmt) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(stmt, conn)


def listar_municipios(modalidade: str | None = None,
                      somente_ativos: bool = False) -> pd.DataFrame:
    stmt = sa.select(municipios)
    if modalidade:
        stmt = stmt.where(municipios.c.modalidade == modalidade)
    if somente_ativos:
        stmt = stmt.where(municipios.c.ativo.is_(True))
    return _read(stmt.order_by(municipios.c.ordem, municipios.c.nome))


def listar_transportadoras(modalidade: str | None = None) -> pd.DataFrame:
    stmt = sa.select(transportadoras)
    if modalidade:
        stmt = stmt.where(transportadoras.c.modalidade == modalidade)
    return _read(stmt.order_by(transportadoras.c.nome))


def listar_veiculos(modalidade: str | None = None) -> pd.DataFrame:
    stmt = sa.select(veiculos)
    if modalidade:
        stmt = stmt.where(veiculos.c.modalidade == modalidade)
    return _read(stmt.order_by(veiculos.c.descricao))


def listar_cargas(modalidade: str | None = None,
                  ano: int | None = None,
                  mes: int | None = None,
                  com_checkout: bool = True) -> pd.DataFrame:
    stmt = sa.select(cargas)
    if modalidade:
        stmt = stmt.where(cargas.c.modalidade == modalidade)
    df = _read(stmt.order_by(cargas.c.data_corte.desc(), cargas.c.id.desc()))
    df = _preparar_cargas(df)

    if com_checkout and not df.empty:
        df = df.merge(resumo_checkout_por_carga(modalidade), on="id", how="left")
        for coluna, padrao in (("notas_total", 0), ("notas_entregues", 0),
                               ("notas_pendentes", 0), ("notas_ocorrencia", 0),
                               ("clientes", 0)):
            df[coluna] = df.get(coluna, padrao)
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce").fillna(0).astype(int)
        df["checkout_pct"] = (
            (df["notas_total"] - df["notas_pendentes"]) / df["notas_total"].replace(0, pd.NA) * 100
        ).fillna(0).round(1)

    if ano is not None and not df.empty:
        df = df[df["ano"] == ano]
    if mes is not None and not df.empty:
        df = df[df["mes"] == mes]
    return df.reset_index(drop=True)


def _preparar_cargas(df: pd.DataFrame) -> pd.DataFrame:
    colunas = ["id", "modalidade", "data_corte", "municipio", "placa", "uf",
               "numcars", "praca", "transportadora", "motorista",
               "data_saida_origem", "previsao_entrega", "data_entrega",
               "status", "ocorrencia", "observacao", "peso_kg", "valor",
               "distancia_km", "origem_dado"]
    for col in colunas:
        if col not in df.columns:
            df[col] = pd.NA

    for col in ("data_corte", "previsao_entrega", "data_entrega", "data_saida_origem"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in ("peso_kg", "valor", "distancia_km"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["ano"] = df["data_corte"].dt.year
    df["mes"] = df["data_corte"].dt.month
    df["dia"] = df["data_corte"].dt.day
    df["peso_t"] = df["peso_kg"] / 1000.0

    atraso = (df["data_entrega"] - df["previsao_entrega"]).dt.days
    df["dias_atraso"] = atraso.where(atraso > 0, 0).fillna(0).astype(int)
    df["entregue"] = df["status"] == "E"
    df["no_prazo"] = df["entregue"] & (df["dias_atraso"] == 0) & df["data_entrega"].notna()
    df["fora_prazo"] = df["entregue"] & (df["dias_atraso"] > 0)
    df["com_ocorrencia"] = (
        df["ocorrencia"].notna()
        & (df["ocorrencia"].astype(str).str.strip() != "")
        & (df["ocorrencia"] != "Sem ocorrência")
    )
    df["identificacao"] = (
        df["data_corte"].dt.strftime("%d/%m/%Y").fillna("—") + " · "
        + df["municipio"].astype(str) + " · "
        + df["placa"].fillna("").astype(str).replace("", "sem placa")
    )
    return df


def listar_notas(modalidade: str | None = None,
                 carga_id: int | None = None) -> pd.DataFrame:
    stmt = sa.select(notas)
    if modalidade:
        stmt = stmt.where(notas.c.modalidade == modalidade)
    if carga_id:
        stmt = stmt.where(notas.c.carga_id == carga_id)
    df = _read(stmt.order_by(notas.c.cliente, notas.c.numnota))
    if df.empty:
        for col in ["id", "carga_id", "modalidade", "numcar", "numnota", "codcli",
                    "cliente", "status", "ocorrencia", "data_checkout",
                    "checkout_em", "observacao"]:
            if col not in df.columns:
                df[col] = pd.NA
        return df
    df["data_checkout"] = pd.to_datetime(df["data_checkout"], errors="coerce")
    if "checkout_em" not in df.columns:
        df["checkout_em"] = pd.NaT
    df["checkout_em"] = pd.to_datetime(df["checkout_em"], errors="coerce")
    df["pendente"] = df["status"] == "P"
    df["entregue"] = df["status"] == "E"
    df["com_ocorrencia"] = (
        df["ocorrencia"].notna()
        & (df["ocorrencia"].astype(str).str.strip() != "")
        & (df["ocorrencia"] != "Sem ocorrência")
    )
    return df


def resumo_checkout_por_carga(modalidade: str | None = None) -> pd.DataFrame:
    """Contagem de notas por carga (total, entregues, pendentes, clientes).

    A soma é feita pelo banco (GROUP BY), não trazendo as notas para o Python —
    é o que mantém a tela leve quando a modalidade acumula milhares de notas.
    """
    entregue = sa.case((notas.c.status == "E", 1), else_=0)
    pendente = sa.case((notas.c.status == "P", 1), else_=0)
    ocorrencia = sa.case(
        (sa.func.coalesce(notas.c.ocorrencia, "Sem ocorrência") != "Sem ocorrência", 1),
        else_=0)

    stmt = sa.select(
        notas.c.carga_id.label("id"),
        sa.func.count(notas.c.id).label("notas_total"),
        sa.func.sum(entregue).label("notas_entregues"),
        sa.func.sum(pendente).label("notas_pendentes"),
        sa.func.sum(ocorrencia).label("notas_ocorrencia"),
        sa.func.count(sa.distinct(notas.c.codcli)).label("clientes"),
    ).group_by(notas.c.carga_id)

    if modalidade:
        stmt = stmt.where(notas.c.modalidade == modalidade)

    df = _read(stmt)
    if df.empty:
        return pd.DataFrame(columns=["id", "notas_total", "notas_entregues",
                                     "notas_pendentes", "notas_ocorrencia", "clientes"])
    return df


def contar_notas_da_carga(carga_id: int) -> dict:
    """Totais de uma única carga, direto no banco."""
    entregue = sa.case((notas.c.status == "E", 1), else_=0)
    pendente = sa.case((notas.c.status == "P", 1), else_=0)
    stmt = sa.select(
        sa.func.count(notas.c.id),
        sa.func.sum(entregue),
        sa.func.sum(pendente),
        sa.func.count(sa.distinct(notas.c.codcli)),
    ).where(notas.c.carga_id == carga_id)
    with get_engine().connect() as conn:
        total, entregues, pendentes, clientes = conn.execute(stmt).first()
    return {"total": int(total or 0), "entregues": int(entregues or 0),
            "pendentes": int(pendentes or 0), "clientes": int(clientes or 0)}


def notas_por_cliente(carga_id: int) -> pd.DataFrame:
    """Uma linha por cliente da carga, com o andamento do checkout."""
    df = listar_notas(carga_id=carga_id)
    if df.empty:
        return pd.DataFrame(columns=["codcli", "cliente", "Notas", "Entregues",
                                     "Pendentes", "Ocorrências"])
    agrupado = df.groupby(["codcli", "cliente"], dropna=False).agg(
        Notas=("id", "count"),
        Entregues=("entregue", "sum"),
        Pendentes=("pendente", "sum"),
        Ocorrências=("com_ocorrencia", "sum"),
    ).reset_index()
    for col in ("Entregues", "Pendentes", "Ocorrências"):
        agrupado[col] = agrupado[col].astype(int)
    return agrupado.sort_values("cliente")


def anos_disponiveis(modalidade: str | None = None) -> list[int]:
    df = listar_cargas(modalidade, com_checkout=False)
    anos = sorted({int(a) for a in df["ano"].dropna().unique()}) if not df.empty else []
    hoje = date.today().year
    if hoje not in anos:
        anos.append(hoje)
    return sorted(anos)


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
def _limpar(valores: dict) -> dict:
    saida = {}
    for k, v in valores.items():
        if isinstance(v, pd.Timestamp):
            v = v.date()
        if v is pd.NaT or (isinstance(v, float) and pd.isna(v)):
            v = None
        saida[k] = v
    return saida


def salvar_carga(dados: dict, carga_id: int | None = None) -> int:
    dados = _limpar(dados)
    with get_engine().begin() as conn:
        if carga_id:
            conn.execute(sa.update(cargas).where(cargas.c.id == carga_id).values(**dados))
            return carga_id
        result = conn.execute(sa.insert(cargas).values(**dados))
        return int(result.inserted_primary_key[0])


def excluir_carga(carga_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(sa.delete(notas).where(notas.c.carga_id == carga_id))
        conn.execute(sa.delete(cargas).where(cargas.c.id == carga_id))


def buscar_carga(modalidade: str, data_corte, municipio: str,
                 placa: str) -> dict | None:
    """Procura a carga pela chave  modalidade + data de corte + município + placa."""
    if isinstance(data_corte, pd.Timestamp):
        data_corte = data_corte.date()
    stmt = sa.select(cargas).where(
        (cargas.c.modalidade == modalidade)
        & (cargas.c.data_corte == data_corte)
        & (sa.func.upper(cargas.c.municipio) == (municipio or "").upper())
        & (sa.func.upper(sa.func.coalesce(cargas.c.placa, "")) == (placa or "").upper())
    )
    with get_engine().connect() as conn:
        linha = conn.execute(stmt).mappings().first()
    return dict(linha) if linha else None


def buscar_programacao(modalidade: str, data_corte, municipio: str) -> dict | None:
    """Carga programada para a data/município cuja placa ainda não foi definida.

    É o caso do corte lançado antes do faturamento: na hora de programar não se
    sabe a placa, então a importação encaixa as notas nessa carga e preenche a
    placa que veio do Wynthor.
    """
    if isinstance(data_corte, pd.Timestamp):
        data_corte = data_corte.date()
    stmt = sa.select(cargas).where(
        (cargas.c.modalidade == modalidade)
        & (cargas.c.data_corte == data_corte)
        & (sa.func.upper(cargas.c.municipio) == (municipio or "").upper())
        & (sa.func.coalesce(cargas.c.placa, "") == "")
    )
    with get_engine().connect() as conn:
        linha = conn.execute(stmt).mappings().first()
    return dict(linha) if linha else None


def listar_programacoes_abertas(modalidade: str) -> pd.DataFrame:
    """Cortes já programados que ainda não receberam notas do Wynthor."""
    df = listar_cargas(modalidade)
    if df.empty:
        return df
    return df[df["notas_total"] == 0].sort_values("data_corte").reset_index(drop=True)


def obter_ou_criar_carga(modalidade: str, data_corte, municipio: str,
                         placa: str, extras: dict | None = None) -> tuple[int, bool]:
    """Devolve (carga_id, foi_criada) para a chave da carga.

    Ordem de busca: carga exata (corte + município + placa); se não achar,
    uma programação do mesmo corte e município ainda sem placa — nesse caso a
    placa do arquivo é gravada nela.
    """
    existente = buscar_carga(modalidade, data_corte, municipio, placa)
    if existente:
        return int(existente["id"]), False

    if placa:
        programada = buscar_programacao(modalidade, data_corte, municipio)
        if programada:
            dados = {"placa": placa}
            dados.update(extras or {})
            salvar_carga(dados, carga_id=int(programada["id"]))
            return int(programada["id"]), False
    dados = {
        "modalidade": modalidade,
        "data_corte": data_corte,
        "municipio": municipio,
        "placa": placa or "",
        "status": "P",
        "ocorrencia": "Sem ocorrência",
    }
    dados.update(extras or {})
    return salvar_carga(dados), True


def numcars_da_carga(carga_id: int) -> list[str]:
    df = listar_notas(carga_id=carga_id)
    if df.empty:
        return []
    return sorted({str(x) for x in df["numcar"].dropna().unique()})


def atualizar_numcars(carga_id: int) -> None:
    lista = numcars_da_carga(carga_id)
    salvar_carga({"numcars": ", ".join(lista) if lista else None}, carga_id=carga_id)


def notas_existentes(carga_id: int) -> set[tuple[str, str]]:
    df = listar_notas(carga_id=carga_id)
    if df.empty:
        return set()
    return {(str(r["numcar"]), str(r["numnota"])) for _, r in df.iterrows()}


def inserir_notas(carga_id: int, modalidade: str,
                  registros: list[dict]) -> dict:
    """Insere notas da carga, pulando as que já existem (mesmo NUMCAR + nota)."""
    existentes = notas_existentes(carga_id)
    novos, repetidas = [], 0
    for reg in registros:
        chave = (str(reg.get("numcar")), str(reg.get("numnota")))
        if chave in existentes:
            repetidas += 1
            continue
        existentes.add(chave)
        novos.append({
            "carga_id": carga_id,
            "modalidade": modalidade,
            "numcar": str(reg.get("numcar") or ""),
            "numnota": str(reg.get("numnota") or ""),
            "codcli": str(reg.get("codcli") or ""),
            "cliente": str(reg.get("cliente") or ""),
            "status": "P",
            "ocorrencia": "Sem ocorrência",
            "data_checkout": None,
            "observacao": None,
        })
    if novos:
        with get_engine().begin() as conn:
            conn.execute(sa.insert(notas), novos)
        atualizar_numcars(carga_id)
        recalcular_status_carga(carga_id)
    return {"inseridas": len(novos), "repetidas": repetidas}


def salvar_nota(dados: dict, nota_id: int) -> None:
    dados = _limpar(dados)
    with get_engine().begin() as conn:
        conn.execute(sa.update(notas).where(notas.c.id == nota_id).values(**dados))


def checkout_notas(ids: list[int], status: str, ocorrencia: str,
                   data_checkout=None, observacao: str | None = None,
                   momento=None) -> int:
    """Dá checkout em várias notas de uma vez (um cliente ou a carga inteira).

    A data e a hora são carimbadas automaticamente no momento do checkout;
    voltar a nota para Pendente limpa esse carimbo.
    """
    if not ids:
        return 0
    momento = momento or agora()
    if isinstance(momento, pd.Timestamp):
        momento = momento.to_pydatetime()
    if data_checkout is None:
        data_checkout = momento.date()
    if isinstance(data_checkout, pd.Timestamp):
        data_checkout = data_checkout.date()

    resolvido = status != "P"
    valores = {
        "status": status,
        "ocorrencia": ocorrencia or "Sem ocorrência",
        "data_checkout": data_checkout if resolvido else None,
        "checkout_em": momento if resolvido else None,
    }
    if observacao is not None:
        valores["observacao"] = observacao or None
    with get_engine().begin() as conn:
        conn.execute(sa.update(notas).where(notas.c.id.in_(ids)).values(**valores))
    return len(ids)


def recalcular_status_carga(carga_id: int) -> str:
    """Status da carga a partir das notas: P / T (parcial) / E / D.

    A contagem é feita pelo banco (uma consulta) e o resultado gravado em um
    único UPDATE — são só duas viagens de rede, o que importa porque isto roda
    a cada checkout.
    """
    resolvida = sa.case((notas.c.status.in_(STATUS_NOTA_RESOLVIDO), 1), else_=0)
    entregue = sa.case((notas.c.status == "E", 1), else_=0)
    devolvida = sa.case((notas.c.status == "D", 1), else_=0)

    # traz as contagens e o status atual da carga na MESMA consulta
    stmt = sa.select(
        sa.func.count(notas.c.id),
        sa.func.sum(resolvida),
        sa.func.sum(entregue),
        sa.func.sum(devolvida),
        sa.func.max(notas.c.data_checkout),
        sa.func.max(cargas.c.status),
        sa.func.max(cargas.c.data_entrega),
    ).select_from(
        cargas.outerjoin(notas, notas.c.carga_id == cargas.c.id)
    ).where(cargas.c.id == carga_id)

    with get_engine().connect() as conn:
        linha = conn.execute(stmt).first()
    if linha is None:
        return "P"
    (total, resolvidas, entregues, devolvidas, ultima,
     status_atual, entrega_atual) = linha

    if not total:
        return status_atual or "P"
    if status_atual == "C":
        return "C"

    resolvidas = int(resolvidas or 0)
    entregues = int(entregues or 0)
    devolvidas = int(devolvidas or 0)

    if resolvidas == 0:
        novo = "P"
    elif resolvidas < int(total):
        novo = "T"
    elif entregues == 0 and devolvidas > 0:
        novo = "D"
    else:
        novo = "E"

    if isinstance(ultima, str):
        ultima = pd.to_datetime(ultima, errors="coerce")
    if isinstance(ultima, pd.Timestamp):
        ultima = ultima.date()

    nova_entrega = ultima if novo in ("E", "D") else None
    if isinstance(entrega_atual, pd.Timestamp):
        entrega_atual = entrega_atual.date()

    # grava só quando algo realmente mudou — economiza uma viagem por clique
    if novo != status_atual or nova_entrega != entrega_atual:
        salvar_carga({"status": novo, "data_entrega": nova_entrega},
                     carga_id=carga_id)
    return novo


def buscar_carga_por_id(carga_id: int) -> dict | None:
    with get_engine().connect() as conn:
        linha = conn.execute(
            sa.select(cargas).where(cargas.c.id == carga_id)).mappings().first()
    return dict(linha) if linha else None


def excluir_nota(nota_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(sa.delete(notas).where(notas.c.id == nota_id))


# ---------------------------------------------------------------------------
# Cadastros
# ---------------------------------------------------------------------------
def salvar_municipio(dados: dict, municipio_id: int | None = None) -> int:
    dados = _limpar(dados)
    with get_engine().begin() as conn:
        if municipio_id:
            conn.execute(sa.update(municipios)
                         .where(municipios.c.id == municipio_id).values(**dados))
            return municipio_id
        return int(conn.execute(sa.insert(municipios).values(**dados)).inserted_primary_key[0])


def excluir_municipio(municipio_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(sa.delete(municipios).where(municipios.c.id == municipio_id))


def salvar_transportadora(dados: dict, registro_id: int | None = None) -> int:
    dados = _limpar(dados)
    with get_engine().begin() as conn:
        if registro_id:
            conn.execute(sa.update(transportadoras)
                         .where(transportadoras.c.id == registro_id).values(**dados))
            return registro_id
        return int(conn.execute(sa.insert(transportadoras).values(**dados)).inserted_primary_key[0])


def excluir_transportadora(registro_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(sa.delete(transportadoras).where(transportadoras.c.id == registro_id))


def salvar_veiculo(dados: dict, registro_id: int | None = None) -> int:
    dados = _limpar(dados)
    with get_engine().begin() as conn:
        if registro_id:
            conn.execute(sa.update(veiculos)
                         .where(veiculos.c.id == registro_id).values(**dados))
            return registro_id
        return int(conn.execute(sa.insert(veiculos).values(**dados)).inserted_primary_key[0])


def excluir_veiculo(registro_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(sa.delete(veiculos).where(veiculos.c.id == registro_id))


def sincronizar_municipio(modalidade: str, nome: str, uf: str = "AM",
                          praca: str | None = None) -> None:
    nome = (nome or "").strip()
    if not nome:
        return
    stmt = sa.select(municipios.c.id).where(
        (municipios.c.modalidade == modalidade)
        & (sa.func.upper(municipios.c.nome) == nome.upper())
    )
    with get_engine().begin() as conn:
        if conn.execute(stmt).first():
            return
        conn.execute(sa.insert(municipios).values(
            modalidade=modalidade, nome=nome, uf=uf or "AM", praca=praca,
            prazo_dias=PRAZO_PADRAO_DIAS, freq_semanal=1, ativo=True, ordem=99,
        ))


def sincronizar_veiculo(modalidade: str, placa: str,
                        motorista: str | None = None) -> None:
    placa = (placa or "").strip()
    if not placa:
        return
    stmt = sa.select(veiculos.c.id).where(
        (veiculos.c.modalidade == modalidade)
        & (sa.func.upper(sa.func.coalesce(veiculos.c.identificacao, "")) == placa.upper())
    )
    with get_engine().begin() as conn:
        if conn.execute(stmt).first():
            return
        conn.execute(sa.insert(veiculos).values(
            modalidade=modalidade, descricao=placa, identificacao=placa,
            motorista=motorista, ativo=True,
        ))


def semear_dados_iniciais() -> None:
    if not listar_municipios(MODALIDADE_PADRAO).empty:
        return
    base = [
        ("AM01", "Manacapuru", 85.0),
        ("AM02", "Autazes", 275.0),
        ("AM03", "Itacoatiara", 185.0),
        ("AM04", "Presidente Figueiredo", 125.0),
        ("AM05", "Silves", 355.0),
    ]
    for ordem, (codigo, nome, km) in enumerate(base, start=1):
        salvar_municipio({
            "modalidade": MODALIDADE_PADRAO, "codigo": codigo, "nome": nome,
            "uf": "AM", "praca": "Am-Rodoviario", "distancia_km": km,
            "prazo_dias": PRAZO_PADRAO_DIAS, "freq_semanal": 1,
            "transportadora_padrao": "Terceiro", "ativo": True, "ordem": ordem,
        })
