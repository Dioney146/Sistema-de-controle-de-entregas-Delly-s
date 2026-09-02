"""Leitura e consolidação do arquivo exportado do Wynthor.

O export vem no nível de **nota fiscal**: várias linhas por carregamento.
Aqui as linhas são agrupadas por `NUMCAR` para virar uma carga do sistema.

Mapeamento pedido:
    NUMCAR  -> Carregamento
    TOTPESO -> Peso (kg)
    DESTINO -> Destino  (ex.: "AM-MANACAPURU 31/08")
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, datetime, timedelta

import pandas as pd

from src.config import PRAZO_PADRAO_DIAS, UFS

COLUNAS_OBRIGATORIAS = ["NUMCAR", "TOTPESO", "DESTINO"]

# Colunas opcionais aproveitadas quando existirem no export
COL_DATA_SAIDA = "DTSAIDA"
COL_VALOR = "VLTOTAL"
COL_NOTA = "NUMNOTA"
COL_CLIENTE = "CODCLI"
COL_PLACA = "PLACA"
COL_MOTORISTA = "NMOTORA"
COL_MUNICIPIO = "MUNICENT"


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(texto))
        if not unicodedata.combining(c)
    )


def ler_arquivo(arquivo) -> pd.DataFrame:
    """Lê .xls (xlrd), .xlsx (openpyxl) ou .csv vindos do Streamlit ou do disco."""
    nome = getattr(arquivo, "name", str(arquivo)).lower()
    dados = arquivo.read() if hasattr(arquivo, "read") else open(arquivo, "rb").read()
    buffer = io.BytesIO(dados)

    if nome.endswith(".csv"):
        return pd.read_csv(buffer, sep=None, engine="python")

    erros = []
    for engine in ("xlrd", "openpyxl", "calamine"):
        try:
            buffer.seek(0)
            return pd.read_excel(buffer, engine=engine)
        except Exception as exc:  # tenta o próximo motor de leitura
            erros.append(f"{engine}: {exc}")
    raise ValueError("Não foi possível ler o arquivo.\n" + "\n".join(erros))


def parse_destino(destino: str) -> dict:
    """Quebra o campo DESTINO em UF, município e data.

    "AM-MANACAPURU 31/08" -> {"uf": "AM", "municipio": "Manacapuru",
                              "dia": 31, "mes": 8}
    """
    texto = str(destino or "").strip()
    resultado = {"uf": None, "municipio": texto.title(), "dia": None, "mes": None}
    if not texto:
        return resultado

    # data no final: 31/08 ou 31/08/2026
    data_match = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\s*$", texto)
    if data_match:
        resultado["dia"] = int(data_match.group(1))
        resultado["mes"] = int(data_match.group(2))
        if data_match.group(3):
            ano = int(data_match.group(3))
            resultado["ano"] = ano + 2000 if ano < 100 else ano
        texto = texto[: data_match.start()].strip()

    # prefixo de UF: "AM-MANACAPURU" ou "AM MANACAPURU"
    uf_match = re.match(r"^([A-Za-z]{2})\s*[-–/]\s*(.+)$", texto)
    if uf_match and uf_match.group(1).upper() in UFS:
        resultado["uf"] = uf_match.group(1).upper()
        texto = uf_match.group(2)

    resultado["municipio"] = re.sub(r"\s+", " ", texto).strip().title()
    return resultado


def _data_saida(grupo: pd.DataFrame, destino_info: dict, ano_ref: int) -> date:
    if COL_DATA_SAIDA in grupo.columns:
        valores = pd.to_datetime(grupo[COL_DATA_SAIDA], errors="coerce").dropna()
        if not valores.empty:
            return valores.min().date()
    if destino_info.get("dia") and destino_info.get("mes"):
        ano = destino_info.get("ano", ano_ref)
        try:
            return date(ano, destino_info["mes"], destino_info["dia"])
        except ValueError:
            pass
    return date.today()


def _data_destino(destino_info: dict, ano_ref: int) -> date | None:
    if destino_info.get("dia") and destino_info.get("mes"):
        ano = destino_info.get("ano", ano_ref)
        try:
            return date(ano, destino_info["mes"], destino_info["dia"])
        except ValueError:
            return None
    return None


def consolidar(df: pd.DataFrame, modalidade: str,
               prazos_por_municipio: dict[str, int] | None = None,
               ano_referencia: int | None = None) -> pd.DataFrame:
    """Agrupa o export por NUMCAR e devolve um DataFrame pronto para o banco."""
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError(
            "O arquivo não tem as colunas obrigatórias: " + ", ".join(faltando)
        )

    prazos = {(_sem_acento(k).upper()): v for k, v in (prazos_por_municipio or {}).items()}
    ano_ref = ano_referencia or date.today().year

    linhas = []
    for (numcar, destino), grupo in df.groupby(["NUMCAR", "DESTINO"], dropna=False):
        info = parse_destino(destino)
        municipio = info["municipio"]

        # se o destino não trouxer o município, usa o mais frequente nas notas
        if (not municipio or municipio.isdigit()) and COL_MUNICIPIO in grupo.columns:
            modo = grupo[COL_MUNICIPIO].dropna()
            if not modo.empty:
                municipio = str(modo.mode().iloc[0]).title()

        saida = _data_saida(grupo, info, ano_ref)
        prazo = prazos.get(_sem_acento(municipio).upper(), PRAZO_PADRAO_DIAS)
        previsao = _data_destino(info, ano_ref) or (saida + timedelta(days=prazo))
        if previsao < saida:
            previsao = saida + timedelta(days=prazo)

        peso = pd.to_numeric(grupo["TOTPESO"], errors="coerce").fillna(0).sum()
        valor = (pd.to_numeric(grupo[COL_VALOR], errors="coerce").fillna(0).sum()
                 if COL_VALOR in grupo.columns else 0.0)
        pedidos = (grupo[COL_NOTA].nunique() if COL_NOTA in grupo.columns else len(grupo))
        clientes = (grupo[COL_CLIENTE].nunique() if COL_CLIENTE in grupo.columns else 0)

        def _primeiro(coluna: str) -> str | None:
            if coluna in grupo.columns:
                valores = grupo[coluna].dropna().astype(str)
                if not valores.empty:
                    return valores.iloc[0].strip()
            return None

        linhas.append({
            "modalidade": modalidade,
            "numcar": str(numcar).strip(),
            "destino_original": str(destino).strip(),
            "data_saida": saida,
            "municipio": municipio,
            "uf": info["uf"] or "AM",
            "praca": None,
            "transportadora": None,
            "motorista": _primeiro(COL_MOTORISTA),
            "veiculo": _primeiro(COL_PLACA),
            "pedidos": int(pedidos),
            "clientes": int(clientes),
            "peso_kg": round(float(peso), 3),
            "valor": round(float(valor), 2),
            "previsao_entrega": previsao,
            "data_entrega": None,
            "status": "P",
            "ocorrencia": "Sem ocorrência",
            "observacao": None,
            "distancia_km": 0.0,
            "origem_dado": "wynthor",
        })

    consolidado = pd.DataFrame(linhas)
    if consolidado.empty:
        return consolidado
    return consolidado.sort_values(["data_saida", "numcar"]).reset_index(drop=True)


def resumo_arquivo(df: pd.DataFrame) -> dict:
    """Números do arquivo bruto, para conferência antes de importar."""
    return {
        "linhas": len(df),
        "carregamentos": int(df["NUMCAR"].nunique()) if "NUMCAR" in df.columns else 0,
        "peso_total_kg": float(pd.to_numeric(
            df.get("TOTPESO", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()),
        "valor_total": float(pd.to_numeric(
            df.get(COL_VALOR, pd.Series(dtype=float)), errors="coerce").fillna(0).sum()),
        "periodo": (
            f"{pd.to_datetime(df[COL_DATA_SAIDA], errors='coerce').min():%d/%m/%Y} a "
            f"{pd.to_datetime(df[COL_DATA_SAIDA], errors='coerce').max():%d/%m/%Y}"
            if COL_DATA_SAIDA in df.columns else "—"
        ),
    }
