"""Indicadores, cronograma mensal e mapa anual."""

from __future__ import annotations

import calendar
from datetime import date

import pandas as pd

from src.config import MESES_CURTOS, STATUS


def kpis(df: pd.DataFrame) -> dict:
    """KPIs de um recorte de cargas (mês ou ano)."""
    if df.empty:
        return {"cargas": 0, "entregues": 0, "conclusao": 0.0, "otif": 0.0,
                "peso_t": 0.0, "valor": 0.0, "fora_prazo": 0, "ocorrencias": 0,
                "municipios": 0, "pedidos": 0}

    validas = df[df["status"] != "C"]
    cargas = len(validas)
    entregues = int(validas["entregue"].sum())
    no_prazo = int(validas["no_prazo"].sum())
    return {
        "cargas": cargas,
        "entregues": entregues,
        "conclusao": (entregues / cargas * 100) if cargas else 0.0,
        "otif": (no_prazo / entregues * 100) if entregues else 0.0,
        "peso_t": float(validas["peso_t"].sum()),
        "valor": float(validas["valor"].sum()),
        "fora_prazo": int(validas["fora_prazo"].sum()),
        "ocorrencias": int(validas["com_ocorrencia"].sum()),
        "municipios": int(validas["municipio"].nunique()),
        "pedidos": int(validas["pedidos"].sum()),
    }


def resumo_por_municipio(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Município", "Cargas", "Entregues",
                                     "% no prazo", "Peso (t)", "Valor (R$)"])
    agrupado = df.groupby("municipio").agg(
        Cargas=("id", "count"),
        Entregues=("entregue", "sum"),
        No_prazo=("no_prazo", "sum"),
        Peso_t=("peso_t", "sum"),
        Valor=("valor", "sum"),
    ).reset_index()
    agrupado["% no prazo"] = (
        agrupado["No_prazo"] / agrupado["Entregues"].replace(0, pd.NA) * 100
    ).fillna(0).round(1)
    agrupado = agrupado.rename(columns={"municipio": "Município",
                                        "Peso_t": "Peso (t)",
                                        "Valor": "Valor (R$)"})
    agrupado["Entregues"] = agrupado["Entregues"].astype(int)
    return agrupado[["Município", "Cargas", "Entregues", "% no prazo",
                     "Peso (t)", "Valor (R$)"]].sort_values("Cargas", ascending=False)


def resumo_por_status(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    total = len(df)
    for codigo, nome in STATUS.items():
        recorte = df[df["status"] == codigo]
        linhas.append({
            "Status": nome,
            "Cargas": len(recorte),
            "% do período": round(len(recorte) / total * 100, 1) if total else 0.0,
            "Peso (t)": round(float(recorte["peso_t"].sum()), 3) if not recorte.empty else 0.0,
        })
    return pd.DataFrame(linhas)


def resumo_por_ocorrencia(df: pd.DataFrame) -> pd.DataFrame:
    recorte = df[df["com_ocorrencia"]]
    if recorte.empty:
        return pd.DataFrame(columns=["Ocorrência", "Cargas", "Peso (t)"])
    agrupado = recorte.groupby("ocorrencia").agg(
        Cargas=("id", "count"), Peso_t=("peso_t", "sum")).reset_index()
    return agrupado.rename(columns={"ocorrencia": "Ocorrência",
                                    "Peso_t": "Peso (t)"}
                           ).sort_values("Cargas", ascending=False)


def matriz_cronograma(df_mes: pd.DataFrame, municipios: list[str],
                      ano: int, mes: int) -> pd.DataFrame:
    """Grade município × dia do mês, no formato da planilha original.

    Célula = código de status (P, T, E...) ou "2x" quando há mais de uma carga.
    """
    dias_no_mes = calendar.monthrange(ano, mes)[1]
    colunas = []
    for dia in range(1, dias_no_mes + 1):
        dia_semana = date(ano, mes, dia).weekday()
        colunas.append(f"{dia:02d}\n{['seg','ter','qua','qui','sex','sáb','dom'][dia_semana]}")

    linhas = {}
    for municipio in municipios:
        linhas[municipio] = {coluna: "" for coluna in colunas}

    if not df_mes.empty:
        for municipio, grupo_mun in df_mes.groupby("municipio"):
            if municipio not in linhas:
                linhas[municipio] = {coluna: "" for coluna in colunas}
            for dia, grupo_dia in grupo_mun.groupby("dia"):
                if pd.isna(dia) or int(dia) > dias_no_mes:
                    continue
                coluna = colunas[int(dia) - 1]
                if len(grupo_dia) > 1:
                    linhas[municipio][coluna] = f"{len(grupo_dia)}x"
                else:
                    linhas[municipio][coluna] = str(grupo_dia.iloc[0]["status"])

    matriz = pd.DataFrame.from_dict(linhas, orient="index")
    matriz.index.name = "Município"
    return matriz.reset_index()


def totais_por_municipio_mes(df_mes: pd.DataFrame,
                             municipios: list[str]) -> pd.DataFrame:
    base = pd.DataFrame({"Município": municipios})
    if df_mes.empty:
        base["Cargas"] = 0
        base["Entregues"] = 0
        base["Peso (t)"] = 0.0
        base["Fora do prazo"] = 0
        return base

    agrupado = df_mes.groupby("municipio").agg(
        Cargas=("id", "count"),
        Entregues=("entregue", "sum"),
        Peso=("peso_t", "sum"),
        Fora=("fora_prazo", "sum"),
    ).reset_index().rename(columns={"municipio": "Município",
                                    "Peso": "Peso (t)",
                                    "Fora": "Fora do prazo"})
    resultado = base.merge(agrupado, on="Município", how="outer").fillna(0)
    for col in ("Cargas", "Entregues", "Fora do prazo"):
        resultado[col] = resultado[col].astype(int)
    resultado["Peso (t)"] = resultado["Peso (t)"].round(3)
    return resultado


INDICADORES_ANUAIS = {
    "Cargas": "cargas",
    "Entregues": "entregues",
    "Peso (t)": "peso",
    "Valor (R$)": "valor",
    "% no prazo": "otif",
    "Pedidos": "pedidos",
}


def mapa_anual(df_ano: pd.DataFrame, municipios: list[str],
               indicador: str = "Cargas") -> pd.DataFrame:
    """Matriz município × mês para o indicador escolhido."""
    matriz = pd.DataFrame(0.0, index=municipios or [], columns=MESES_CURTOS)
    matriz.index.name = "Município"

    if not df_ano.empty:
        for municipio, grupo_mun in df_ano.groupby("municipio"):
            if municipio not in matriz.index:
                matriz.loc[municipio] = 0.0
            for mes, grupo in grupo_mun.groupby("mes"):
                if pd.isna(mes):
                    continue
                coluna = MESES_CURTOS[int(mes) - 1]
                if indicador == "Cargas":
                    valor = len(grupo)
                elif indicador == "Entregues":
                    valor = int(grupo["entregue"].sum())
                elif indicador == "Peso (t)":
                    valor = round(float(grupo["peso_t"].sum()), 3)
                elif indicador == "Valor (R$)":
                    valor = round(float(grupo["valor"].sum()), 2)
                elif indicador == "Pedidos":
                    valor = int(grupo["pedidos"].sum())
                elif indicador == "% no prazo":
                    entregues = int(grupo["entregue"].sum())
                    valor = round(int(grupo["no_prazo"].sum()) / entregues * 100, 1) if entregues else 0.0
                else:
                    valor = len(grupo)
                matriz.loc[municipio, coluna] = valor

    if indicador == "% no prazo":
        matriz["Total ano"] = matriz.replace(0, pd.NA).mean(axis=1).fillna(0).round(1)
    else:
        matriz["Total ano"] = matriz.sum(axis=1).round(3)
    return matriz.reset_index()


def resumo_mensal_operacao(df_ano: pd.DataFrame) -> pd.DataFrame:
    """Linhas de resumo (cargas, entregues, peso, valor...) por mês do ano."""
    linhas = {
        "Cargas programadas": [], "Cargas entregues": [], "Fora do prazo": [],
        "% no prazo": [], "Peso (t)": [], "Valor (R$)": [], "Ocorrências": [],
    }
    for mes in range(1, 13):
        recorte = df_ano[df_ano["mes"] == mes] if not df_ano.empty else df_ano
        indicadores = kpis(recorte)
        linhas["Cargas programadas"].append(indicadores["cargas"])
        linhas["Cargas entregues"].append(indicadores["entregues"])
        linhas["Fora do prazo"].append(indicadores["fora_prazo"])
        linhas["% no prazo"].append(round(indicadores["otif"], 1))
        linhas["Peso (t)"].append(round(indicadores["peso_t"], 3))
        linhas["Valor (R$)"].append(round(indicadores["valor"], 2))
        linhas["Ocorrências"].append(indicadores["ocorrencias"])

    resumo = pd.DataFrame(linhas, index=MESES_CURTOS).T
    resumo["Total"] = resumo.sum(axis=1)
    resumo.loc["% no prazo", "Total"] = round(
        resumo.loc["% no prazo", MESES_CURTOS].replace(0, pd.NA).mean(), 1
    ) if resumo.loc["% no prazo", MESES_CURTOS].sum() else 0.0
    resumo.index.name = "Indicador"
    return resumo.reset_index()


def serie_diaria(df_mes: pd.DataFrame, ano: int, mes: int) -> pd.DataFrame:
    """Peso e cargas por dia do mês (para gráficos)."""
    dias = calendar.monthrange(ano, mes)[1]
    base = pd.DataFrame({"dia": range(1, dias + 1)})
    if df_mes.empty:
        base["Cargas"] = 0
        base["Peso (t)"] = 0.0
        return base
    agrupado = df_mes.groupby("dia").agg(
        Cargas=("id", "count"), Peso=("peso_t", "sum")).reset_index()
    resultado = base.merge(agrupado, on="dia", how="left").fillna(0)
    return resultado.rename(columns={"Peso": "Peso (t)"})
