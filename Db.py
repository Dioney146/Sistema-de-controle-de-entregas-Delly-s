"""Camada de banco de dados.

Funciona em dois modos, sem mudar o código:

* **Local / GitHub Codespaces** — SQLite em `data/dellys_entregas.db`
* **Streamlit Cloud** — Postgres (Supabase, Neon, Railway...) via
  `st.secrets["database"]["url"]`

O sistema de arquivos do Streamlit Cloud é efêmero: se você publicar o app
usando SQLite, os dados somem a cada redeploy/reinício. Para produção use
Postgres e coloque a URL em `.streamlit/secrets.toml`.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Integer, MetaData,
    String, Table, UniqueConstraint, func,
)

from src.config import MODALIDADE_PADRAO, PRAZO_PADRAO_DIAS

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
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
    Column("descricao", String(80), nullable=False),   # veículo ou embarcação
    Column("identificacao", String(30)),               # placa / registro da balsa
    Column("motorista", String(80)),                   # motorista ou responsável
    Column("telefone", String(30)),
    Column("transportadora", String(80)),
    Column("ativo", Boolean, default=True),
    UniqueConstraint("modalidade", "descricao", "identificacao",
                     name="uq_veiculo_modalidade"),
)

cargas = Table(
    "cargas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("modalidade", String(20), nullable=False),
    Column("numcar", String(30)),                      # carregamento (Wynthor)
    Column("data_saida", Date, nullable=False),        # data de corte / saída
    Column("municipio", String(120), nullable=False),
    Column("uf", String(2), default="AM"),
    Column("praca", String(60)),
    Column("transportadora", String(80)),
    Column("motorista", String(80)),
    Column("veiculo", String(80)),                     # placa ou embarcação
    Column("pedidos", Integer, default=0),
    Column("clientes", Integer, default=0),
    Column("peso_kg", Float, default=0.0),
    Column("valor", Float, default=0.0),
    Column("previsao_entrega", Date),
    Column("data_entrega", Date),
    Column("status", String(1), default="P"),
    Column("ocorrencia", String(60), default="Sem ocorrência"),
    Column("observacao", String(400)),
    Column("distancia_km", Float, default=0.0),
    Column("origem_dado", String(20), default="manual"),  # manual | wynthor
    Column("criado_em", DateTime, server_default=func.now()),
    UniqueConstraint("modalidade", "numcar", name="uq_carga_numcar"),
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
    if url.startswith("postgres://"):  # normaliza URLs antigas do Heroku/Supabase
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
    return sa.create_engine(url, **kwargs)


try:  # cache do engine quando rodando dentro do Streamlit
    import streamlit as st

    @st.cache_resource(show_spinner=False)
    def get_engine() -> sa.Engine:
        return _build_engine()
except Exception:  # execução fora do Streamlit (scripts, testes)
    _ENGINE: sa.Engine | None = None

    def get_engine() -> sa.Engine:  # type: ignore[misc]
        global _ENGINE
        if _ENGINE is None:
            _ENGINE = _build_engine()
        return _ENGINE


def init_db() -> None:
    """Cria as tabelas se ainda não existirem."""
    metadata.create_all(get_engine())


def is_sqlite() -> bool:
    return get_engine().dialect.name == "sqlite"


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
    stmt = stmt.order_by(municipios.c.ordem, municipios.c.nome)
    return _read(stmt)


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
                  mes: int | None = None) -> pd.DataFrame:
    """Cargas com colunas derivadas (ano, mês, dia, atraso, no_prazo)."""
    stmt = sa.select(cargas)
    if modalidade:
        stmt = stmt.where(cargas.c.modalidade == modalidade)
    df = _read(stmt.order_by(cargas.c.data_saida.desc(), cargas.c.id.desc()))
    if df.empty:
        return _preparar_colunas(df)

    df = _preparar_colunas(df)
    if ano is not None:
        df = df[df["ano"] == ano]
    if mes is not None:
        df = df[df["mes"] == mes]
    return df.reset_index(drop=True)


def _preparar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos e cria colunas calculadas usadas nos relatórios."""
    colunas = ["id", "modalidade", "numcar", "data_saida", "municipio", "uf",
               "praca", "transportadora", "motorista", "veiculo", "pedidos",
               "clientes", "peso_kg", "valor", "previsao_entrega",
               "data_entrega", "status", "ocorrencia", "observacao",
               "distancia_km", "origem_dado"]
    for col in colunas:
        if col not in df.columns:
            df[col] = pd.NA

    for col in ("data_saida", "previsao_entrega", "data_entrega"):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    for col in ("peso_kg", "valor", "distancia_km"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    for col in ("pedidos", "clientes"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["ano"] = df["data_saida"].dt.year
    df["mes"] = df["data_saida"].dt.month
    df["dia"] = df["data_saida"].dt.day
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
    return df


def anos_disponiveis(modalidade: str | None = None) -> list[int]:
    df = listar_cargas(modalidade)
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
    """Insere ou atualiza uma carga. Retorna o id."""
    dados = _limpar(dados)
    with get_engine().begin() as conn:
        if carga_id:
            conn.execute(sa.update(cargas).where(cargas.c.id == carga_id).values(**dados))
            return carga_id
        result = conn.execute(sa.insert(cargas).values(**dados))
        return int(result.inserted_primary_key[0])


def excluir_carga(carga_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(sa.delete(cargas).where(cargas.c.id == carga_id))


def numcars_existentes(modalidade: str) -> set[str]:
    stmt = sa.select(cargas.c.numcar).where(cargas.c.modalidade == modalidade)
    df = _read(stmt)
    if df.empty:
        return set()
    return {str(x) for x in df["numcar"].dropna().tolist()}


def inserir_cargas_em_lote(registros: list[dict]) -> dict:
    """Insere várias cargas ignorando NUMCAR já existente na modalidade.

    Retorna {"inseridos": n, "ignorados": [numcar, ...]}.
    """
    inseridos, ignorados = 0, []
    for reg in registros:
        existentes = numcars_existentes(reg["modalidade"])
        numcar = str(reg.get("numcar") or "")
        if numcar and numcar in existentes:
            ignorados.append(numcar)
            continue
        salvar_carga(reg)
        inseridos += 1
    return {"inseridos": inseridos, "ignorados": ignorados}


def salvar_municipio(dados: dict, municipio_id: int | None = None) -> int:
    dados = _limpar(dados)
    with get_engine().begin() as conn:
        if municipio_id:
            conn.execute(sa.update(municipios)
                         .where(municipios.c.id == municipio_id).values(**dados))
            return municipio_id
        result = conn.execute(sa.insert(municipios).values(**dados))
        return int(result.inserted_primary_key[0])


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
        result = conn.execute(sa.insert(transportadoras).values(**dados))
        return int(result.inserted_primary_key[0])


def excluir_transportadora(registro_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(sa.delete(transportadoras)
                     .where(transportadoras.c.id == registro_id))


def salvar_veiculo(dados: dict, registro_id: int | None = None) -> int:
    dados = _limpar(dados)
    with get_engine().begin() as conn:
        if registro_id:
            conn.execute(sa.update(veiculos)
                         .where(veiculos.c.id == registro_id).values(**dados))
            return registro_id
        result = conn.execute(sa.insert(veiculos).values(**dados))
        return int(result.inserted_primary_key[0])


def excluir_veiculo(registro_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(sa.delete(veiculos).where(veiculos.c.id == registro_id))


def sincronizar_municipio(modalidade: str, nome: str, uf: str = "AM",
                          praca: str | None = None) -> None:
    """Garante que um município importado exista no cadastro da modalidade."""
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
            modalidade=modalidade, nome=nome, uf=uf or "AM",
            praca=praca, prazo_dias=PRAZO_PADRAO_DIAS,
            freq_semanal=1, ativo=True, ordem=99,
        ))


def semear_dados_iniciais() -> None:
    """Popula os municípios rodoviários da planilha original (só na 1ª vez)."""
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
