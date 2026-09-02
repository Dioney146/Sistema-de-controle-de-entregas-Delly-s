"""Leitura do export do Wynthor no nível de NOTA FISCAL.

Colunas usadas hoje (por enquanto, só estas quatro):
    CODCLI  -> Código do cliente
    CLIENTE -> Cliente
    NUMNOTA -> Nota fiscal
    NUMCAR  -> Carregamento

Para montar a carga também são lidos DESTINO (município/UF) e PLACA, porque a
carga é identificada por **data de corte + município + placa**. A data de corte
NÃO vem do arquivo — ela é informada manualmente na tela de importação, já que
o DTSAIDA do Wynthor não corresponde ao corte real.

Uma mesma placa pode levar mais de um carregamento na mesma viagem: nesse caso
os dois NUMCAR caem na mesma carga, e cada nota guarda o seu carregamento.
"""

from __future__ import annotations

import io
import re
import unicodedata

import pandas as pd

from src.config import UFS

# Colunas de nota (obrigatórias)
COL_CODCLI = "CODCLI"
COL_CLIENTE = "CLIENTE"
COL_NUMNOTA = "NUMNOTA"
COL_NUMCAR = "NUMCAR"
COLUNAS_OBRIGATORIAS = [COL_CODCLI, COL_CLIENTE, COL_NUMNOTA, COL_NUMCAR]

# Colunas usadas para montar a carga (opcionais — dá para preencher na tela)
COL_DESTINO = "DESTINO"
COL_PLACA = "PLACA"
COL_MUNICIPIO = "MUNICENT"
COL_DTSAIDA = "DTSAIDA"
COL_MOTORISTA = "NMOTORA"
COL_PESO = "TOTPESO"
COL_VALOR = "VLTOTAL"

SEPARADOR_GRUPO = " || "


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto))
                   if not unicodedata.combining(c))


def ler_arquivo(arquivo) -> pd.DataFrame:
    """Lê .xls (xlrd), .xlsx (openpyxl) ou .csv, vindo do Streamlit ou do disco."""
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
        except Exception as exc:
            erros.append(f"{engine}: {exc}")
    raise ValueError("Não foi possível ler o arquivo.\n" + "\n".join(erros))


def parse_destino(destino: str) -> dict:
    """"AM-MANACAPURU 31/08" -> {"uf": "AM", "municipio": "Manacapuru"}."""
    texto = str(destino or "").strip()
    resultado = {"uf": None, "municipio": texto.title()}
    if not texto:
        return resultado

    texto = re.sub(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\s*$", "", texto).strip()

    uf_match = re.match(r"^([A-Za-z]{2})\s*[-–/]\s*(.+)$", texto)
    if uf_match and uf_match.group(1).upper() in UFS:
        resultado["uf"] = uf_match.group(1).upper()
        texto = uf_match.group(2)

    resultado["municipio"] = re.sub(r"\s+", " ", texto).strip().title()
    return resultado


def validar(df: pd.DataFrame) -> None:
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError("O arquivo não tem as colunas obrigatórias: "
                         + ", ".join(faltando))


def preparar_notas(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por nota fiscal, já com o grupo (município + placa) sugerido."""
    validar(df)
    base = pd.DataFrame({
        "numcar": df[COL_NUMCAR].astype(str).str.strip(),
        "numnota": df[COL_NUMNOTA].astype(str).str.strip(),
        "codcli": df[COL_CODCLI].astype(str).str.strip(),
        "cliente": df[COL_CLIENTE].astype(str).str.strip(),
    })

    if COL_DESTINO in df.columns:
        destinos = df[COL_DESTINO].apply(parse_destino)
        base["municipio"] = [d["municipio"] for d in destinos]
        base["uf"] = [d["uf"] or "AM" for d in destinos]
        base["destino_original"] = df[COL_DESTINO].astype(str).str.strip()
    else:
        base["municipio"] = ""
        base["uf"] = "AM"
        base["destino_original"] = ""

    vazio = base["municipio"].astype(str).str.strip() == ""
    if vazio.any() and COL_MUNICIPIO in df.columns:
        base.loc[vazio, "municipio"] = (
            df.loc[vazio, COL_MUNICIPIO].astype(str).str.title())

    base["placa"] = (df[COL_PLACA].astype(str).str.strip().str.upper()
                     if COL_PLACA in df.columns else "")
    base["placa"] = base["placa"].replace({"NAN": "", "NONE": ""}).fillna("")
    base["motorista"] = (df[COL_MOTORISTA].astype(str).str.strip()
                         if COL_MOTORISTA in df.columns else "")
    base["peso_kg"] = (pd.to_numeric(df[COL_PESO], errors="coerce").fillna(0.0)
                       if COL_PESO in df.columns else 0.0)
    base["valor"] = (pd.to_numeric(df[COL_VALOR], errors="coerce").fillna(0.0)
                     if COL_VALOR in df.columns else 0.0)
    base["data_saida_origem"] = (pd.to_datetime(df[COL_DTSAIDA], errors="coerce")
                                 if COL_DTSAIDA in df.columns else pd.NaT)

    base["grupo"] = base["municipio"].astype(str) + SEPARADOR_GRUPO + base["placa"].astype(str)
    return base


def resumir_grupos(notas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por carga sugerida (município + placa), para conferir na tela."""
    if notas.empty:
        return pd.DataFrame(columns=["grupo", "Município", "UF", "Placa",
                                     "Carregamentos", "Notas", "Clientes"])
    linhas = []
    for grupo, dados in notas.groupby("grupo", dropna=False):
        carregamentos = sorted({str(x) for x in dados["numcar"].dropna().unique()})
        saidas = dados["data_saida_origem"].dropna()
        linhas.append({
            "grupo": grupo,
            "Município": dados["municipio"].iloc[0],
            "UF": dados["uf"].iloc[0],
            "Placa": dados["placa"].iloc[0],
            "Carregamentos": ", ".join(carregamentos),
            "Notas": int(dados["numnota"].nunique()),
            "Clientes": int(dados["codcli"].nunique()),
            "Peso (kg)": round(float(dados["peso_kg"].sum()), 3),
            "Valor (R$)": round(float(dados["valor"].sum()), 2),
            "Saída no Wynthor": saidas.min().date() if not saidas.empty else None,
        })
    return pd.DataFrame(linhas).sort_values(["Município", "Placa"]).reset_index(drop=True)


def resumo_arquivo(df: pd.DataFrame) -> dict:
    """Números do arquivo bruto, para conferência antes de importar."""
    resumo = {
        "linhas": len(df),
        "notas": int(df[COL_NUMNOTA].nunique()) if COL_NUMNOTA in df.columns else 0,
        "clientes": int(df[COL_CODCLI].nunique()) if COL_CODCLI in df.columns else 0,
        "carregamentos": int(df[COL_NUMCAR].nunique()) if COL_NUMCAR in df.columns else 0,
    }
    if COL_DTSAIDA in df.columns:
        datas = pd.to_datetime(df[COL_DTSAIDA], errors="coerce").dropna()
        resumo["saida_wynthor"] = (f"{datas.min():%d/%m/%Y} a {datas.max():%d/%m/%Y}"
                                   if not datas.empty else "—")
    else:
        resumo["saida_wynthor"] = "—"
    return resumo
