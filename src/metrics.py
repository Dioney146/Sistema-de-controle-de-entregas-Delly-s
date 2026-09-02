"""Indicadores, cronograma mensal e mapa anual."""

from __future__ import annotations

import calendar
from datetime import date

import pandas as pd

from src.config import DIAS_SEMANA_CURTOS, MESES_CURTOS, STATUS


def kpis(df: pd.DataFrame) -> dict:
    """KPIs de um recorte de cargas (mês ou ano)."""
    vazio = {"cargas": 0, "entregues": 0, "conclusao": 0.0, "otif": 0.0,
             "peso_t": 0.0, "valor": 0.0, "fora_prazo": 0, "ocorrencias": 0,
             "municipios": 0, "notas": 0, "notas_entregues": 0,
             "notas_pendentes": 0, "notas_ocorrencia": 0, "checkout": 0.0,
             "clientes": 0}
    if df.empty:
        return vazio

    validas = df[df["status"] != "C"]
    if validas.empty:
        return vazio

    cargas = len(validas)
    entregues = int(validas["entregue"].sum())
    no_prazo = int(validas["no_prazo"].sum())
    notas_total = int(validas.get("notas_total", pd.Series(0, index=validas.index)).sum())
    notas_pend = int(validas.get("notas_pendentes", pd.Series(0, index=validas.index)).sum())

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
        "notas": notas_total,
        "notas_entregues": int(validas.get("notas_entregues", pd.Series(0, index=validas.index)).sum()),
        "notas_pendentes": notas_pend,
        "notas_ocorrencia": int(validas.get("notas_ocorrencia", pd.Series(0, index=validas.index)).sum()),
        "checkout": ((notas_total - notas_pend) / notas_total * 100) if notas_total else 0.0,
        "clientes": int(validas.get("clientes", pd.Series(0, index=validas.index)).sum()),
    }


def resumo_por_municipio(df: pd.DataFrame) -> pd.DataFrame:
    colunas = ["Município", "Cargas", "Entregues", "% no prazo", "Notas",
               "Notas entregues", "Peso (t)", "Valor (R$)"]
    if df.empty:
        return pd.DataFrame(columns=colunas)

    trabalho = df.copy()
    for coluna in ("notas_total", "notas_entregues"):
        if coluna not in trabalho.columns:
            trabalho[coluna] = 0

    agrupado = trabalho.groupby("municipio").agg(
        Cargas=("id", "count"),
        Entregues=("entregue", "sum"),
        No_prazo=("no_prazo", "sum"),
        Notas=("notas_total", "sum"),
        Notas_entregues=("notas_entregues", "sum"),
        Peso_t=("peso_t", "sum"),
        Valor=("valor", "sum"),
    ).reset_index()
    agrupado["% no prazo"] = (
        agrupado["No_prazo"] / agrupado["Entregues"].replace(0, pd.NA) * 100
    ).fillna(0).round(1)
    agrupado = agrupado.rename(columns={"municipio": "Município",
                                        "Notas_entregues": "Notas entregues",
                                        "Peso_t": "Peso (t)", "Valor": "Valor (R$)"})
    agrupado["Entregues"] = agrupado["Entregues"].astype(int)
    return agrupado[colunas].sort_values("Cargas", ascending=False)


def resumo_por_status(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    total = len(df)
    for codigo, nome in STATUS.items():
        recorte = df[df["status"] == codigo] if not df.empty else df
        linhas.append({
            "Status": nome,
            "Cargas": len(recorte),
            "% do período": round(len(recorte) / total * 100, 1) if total else 0.0,
            "Peso (t)": round(float(recorte["peso_t"].sum()), 3) if not recorte.empty else 0.0,
        })
    return pd.DataFrame(linhas)


def resumo_por_ocorrencia(df_notas: pd.DataFrame) -> pd.DataFrame:
    """Ocorrências no nível da NOTA (é onde elas são registradas no checkout)."""
    if df_notas.empty:
        return pd.DataFrame(columns=["Ocorrência", "Notas", "Clientes"])
    recorte = df_notas[df_notas["com_ocorrencia"]]
    if recorte.empty:
        return pd.DataFrame(columns=["Ocorrência", "Notas", "Clientes"])
    agrupado = recorte.groupby("ocorrencia").agg(
        Notas=("id", "count"), Clientes=("codcli", "nunique")).reset_index()
    return agrupado.rename(columns={"ocorrencia": "Ocorrência"}
                           ).sort_values("Notas", ascending=False)


def matriz_cronograma(df_mes: pd.DataFrame, municipios: list[str],
                      ano: int, mes: int) -> pd.DataFrame:
    """Grade município × dia da data de corte, no formato da planilha original."""
    dias_no_mes = calendar.monthrange(ano, mes)[1]
    colunas = []
    for dia in range(1, dias_no_mes + 1):
        colunas.append(f"{dia:02d}\n{DIAS_SEMANA_CURTOS[date(ano, mes, dia).weekday()]}")

    linhas = {municipio: {coluna: "" for coluna in colunas} for municipio in municipios}

    if not df_mes.empty:
        for municipio, grupo_mun in df_mes.groupby("municipio"):
            if municipio not in linhas:
                linhas[municipio] = {coluna: "" for coluna in colunas}
            for dia, grupo_dia in grupo_mun.groupby("dia"):
                if pd.isna(dia) or int(dia) > dias_no_mes:
                    continue
                coluna = colunas[int(dia) - 1]
                linhas[municipio][coluna] = (f"{len(grupo_dia)}x" if len(grupo_dia) > 1
                                             else str(grupo_dia.iloc[0]["status"]))

    matriz = pd.DataFrame.from_dict(linhas, orient="index")
    matriz.index.name = "Município"
    return matriz.reset_index()


def totais_por_municipio_mes(df_mes: pd.DataFrame,
                             municipios: list[str]) -> pd.DataFrame:
    base = pd.DataFrame({"Município": municipios})
    if df_mes.empty:
        base["Cargas"] = 0
        base["Entregues"] = 0
        base["Notas"] = 0
        base["Peso (t)"] = 0.0
        base["Fora do prazo"] = 0
        return base

    trabalho = df_mes.copy()
    if "notas_total" not in trabalho.columns:
        trabalho["notas_total"] = 0

    agrupado = trabalho.groupby("municipio").agg(
        Cargas=("id", "count"),
        Entregues=("entregue", "sum"),
        Notas=("notas_total", "sum"),
        Peso=("peso_t", "sum"),
        Fora=("fora_prazo", "sum"),
    ).reset_index().rename(columns={"municipio": "Município", "Peso": "Peso (t)",
                                    "Fora": "Fora do prazo"})
    resultado = base.merge(agrupado, on="Município", how="outer").fillna(0)
    for col in ("Cargas", "Entregues", "Notas", "Fora do prazo"):
        resultado[col] = resultado[col].astype(int)
    resultado["Peso (t)"] = resultado["Peso (t)"].round(3)
    return resultado


INDICADORES_ANUAIS = {
    "Cargas": "cargas",
    "Entregues": "entregues",
    "Notas": "notas",
    "Peso (t)": "peso",
    "Valor (R$)": "valor",
    "% no prazo": "otif",
}


def mapa_anual(df_ano: pd.DataFrame, municipios: list[str],
               indicador: str = "Cargas") -> pd.DataFrame:
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
                elif indicador == "Notas":
                    valor = int(grupo.get("notas_total", pd.Series(0, index=grupo.index)).sum())
                elif indicador == "Peso (t)":
                    valor = round(float(grupo["peso_t"].sum()), 3)
                elif indicador == "Valor (R$)":
                    valor = round(float(grupo["valor"].sum()), 2)
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
    linhas = {
        "Cargas programadas": [], "Cargas entregues": [], "Notas": [],
        "Notas entregues": [], "Fora do prazo": [], "% no prazo": [],
        "Peso (t)": [], "Valor (R$)": [], "Ocorrências": [],
    }
    for mes in range(1, 13):
        recorte = df_ano[df_ano["mes"] == mes] if not df_ano.empty else df_ano
        indicadores = kpis(recorte)
        linhas["Cargas programadas"].append(indicadores["cargas"])
        linhas["Cargas entregues"].append(indicadores["entregues"])
        linhas["Notas"].append(indicadores["notas"])
        linhas["Notas entregues"].append(indicadores["notas_entregues"])
        linhas["Fora do prazo"].append(indicadores["fora_prazo"])
        linhas["% no prazo"].append(round(indicadores["otif"], 1))
        linhas["Peso (t)"].append(round(indicadores["peso_t"], 3))
        linhas["Valor (R$)"].append(round(indicadores["valor"], 2))
        linhas["Ocorrências"].append(indicadores["notas_ocorrencia"])

    resumo = pd.DataFrame(linhas, index=MESES_CURTOS).T
    resumo["Total"] = resumo.sum(axis=1)
    if resumo.loc["% no prazo", MESES_CURTOS].sum():
        resumo.loc["% no prazo", "Total"] = round(
            resumo.loc["% no prazo", MESES_CURTOS].replace(0, pd.NA).mean(), 1)
    else:
        resumo.loc["% no prazo", "Total"] = 0.0
    resumo.index.name = "Indicador"
    return resumo.reset_index()


def serie_diaria(df_mes: pd.DataFrame, ano: int, mes: int) -> pd.DataFrame:
    dias = calendar.monthrange(ano, mes)[1]
    base = pd.DataFrame({"dia": range(1, dias + 1)})
    if df_mes.empty:
        base["Cargas"] = 0
        base["Notas"] = 0
        return base
    trabalho = df_mes.copy()
    if "notas_total" not in trabalho.columns:
        trabalho["notas_total"] = 0
    agrupado = trabalho.groupby("dia").agg(
        Cargas=("id", "count"), Notas=("notas_total", "sum")).reset_index()
    return base.merge(agrupado, on="dia", how="left").fillna(0)


def ranking_clientes(df_notas: pd.DataFrame, limite: int = 15) -> pd.DataFrame:
    """Clientes com mais notas não entregues no período."""
    if df_notas.empty:
        return pd.DataFrame(columns=["Cliente", "Notas", "Entregues", "Pendentes"])
    agrupado = df_notas.groupby(["codcli", "cliente"], dropna=False).agg(
        Notas=("id", "count"),
        Entregues=("entregue", "sum"),
        Pendentes=("pendente", "sum"),
    ).reset_index().rename(columns={"cliente": "Cliente"})
    for col in ("Entregues", "Pendentes"):
        agrupado[col] = agrupado[col].astype(int)
    return (agrupado.sort_values(["Pendentes", "Notas"], ascending=False)
            .head(limite)[["Cliente", "Notas", "Entregues", "Pendentes"]])
