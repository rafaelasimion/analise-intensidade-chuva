"""Agregações: série para gráficos, resumo do período, diário e relatórios."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from .config import LIMIAR_DIA_CHUVA_MM

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _num(x, casas: int = 2):
    """float seguro para JSON (NaN -> None)."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, casas)


def _iso(ts) -> str | None:
    if ts is None or (isinstance(ts, float) and math.isnan(ts)) or pd.isna(ts):
        return None
    return pd.Timestamp(ts).isoformat()


def _max_com_momento(df: pd.DataFrame, coluna: str, momento: str = "data_hora") -> dict:
    if coluna not in df or df[coluna].notna().sum() == 0:
        return {"valor": None, "quando": None}
    i = df[coluna].idxmax()
    return {"valor": _num(df.at[i, coluna]), "quando": _iso(df.at[i, momento])}


def _min_com_momento(df: pd.DataFrame, coluna: str, momento: str = "data_hora") -> dict:
    if coluna not in df or df[coluna].notna().sum() == 0:
        return {"valor": None, "quando": None}
    i = df[coluna].idxmin()
    return {"valor": _num(df.at[i, coluna]), "quando": _iso(df.at[i, momento])}


def variaveis_com_dados(df: pd.DataFrame) -> list[str]:
    candidatas = [
        "chuva_mm", "temp_c", "temp_max_c", "temp_min_c", "ur_pct", "vento_ms",
        "vento_max_ms", "vento_dir_graus", "rad_w_m2", "pressao_hpa",
    ]
    return [c for c in candidatas if c in df and df[c].notna().any()]


def registros_esperados_por_dia(df15: pd.DataFrame) -> float:
    if "intervalo_h" in df15 and df15["intervalo_h"].notna().any():
        modal = df15["intervalo_h"].mode()
        if len(modal) and modal.iloc[0] > 0:
            return 24 / float(modal.iloc[0])
    return 96.0


# ---------------------------------------------------------------------------
# Diário a partir dos dados de 15 min
# ---------------------------------------------------------------------------


def diario_de_15min(df15: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por dia (dia = fim do intervalo de 15 min)."""
    colunas = [
        "dia", "chuva_mm", "intensidade_max_mm_h", "temp_c", "temp_max_c", "temp_min_c",
        "ur_pct", "vento_ms", "vento_max_ms", "rad_mj_m2", "pressao_hpa", "registros", "cobertura_pct",
    ]
    if df15.empty:
        return pd.DataFrame(columns=colunas)

    esperado = registros_esperados_por_dia(df15)
    g = df15.groupby("dia")

    temp_max = g["temp_max_c"].max() if df15["temp_max_c"].notna().any() else g["temp_c"].max()
    temp_min = g["temp_min_c"].min() if df15["temp_min_c"].notna().any() else g["temp_c"].min()
    # Se o arquivo tiver máx/mín só em parte do período, completa com a média de 15 min
    temp_max = temp_max.fillna(g["temp_c"].max())
    temp_min = temp_min.fillna(g["temp_c"].min())

    vento_max = g["vento_max_ms"].max()

    rad_media = g["rad_w_m2"].mean()
    rad_cont = g["rad_w_m2"].count()
    rad_mj = (rad_media * 0.0864).where(rad_cont >= 0.9 * esperado)

    validos = g["chuva_mm"].count()
    diario = pd.DataFrame({
        "chuva_mm": g["chuva_mm"].sum(min_count=1),
        "intensidade_max_mm_h": g["intensidade_mm_h"].max(),
        "temp_c": g["temp_c"].mean(),
        "temp_max_c": temp_max,
        "temp_min_c": temp_min,
        "ur_pct": g["ur_pct"].mean(),
        "vento_ms": g["vento_ms"].mean(),
        "vento_max_ms": vento_max,
        "rad_mj_m2": rad_mj,
        "pressao_hpa": g["pressao_hpa"].mean(),
        "registros": g.size(),
        "cobertura_pct": (validos / esperado * 100).clip(upper=100),
    })
    diario.index.name = "dia"
    return diario.reset_index()[colunas]


# ---------------------------------------------------------------------------
# Resumo do período (cartões do painel)
# ---------------------------------------------------------------------------


def resumo(df15: pd.DataFrame, diario: pd.DataFrame, inicio: date, fim: date) -> dict:
    dias_periodo = (fim - inicio).days + 1
    esperado = registros_esperados_por_dia(df15) * dias_periodo
    chuva_validos = int(df15["chuva_mm"].count()) if not df15.empty else 0

    return {
        "periodo": {
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
            "dias": dias_periodo,
            "primeiro_registro": _iso(df15["data_hora"].min()) if not df15.empty else None,
            "ultimo_registro": _iso(df15["data_hora"].max()) if not df15.empty else None,
        },
        "registros": int(len(df15)),
        "cobertura_pct": _num(min(100.0, chuva_validos / esperado * 100) if esperado else None, 1),
        "chuva_total_mm": _num(df15["chuva_mm"].sum(min_count=1)) if not df15.empty else None,
        "dias_chuva": int((diario["chuva_mm"] >= LIMIAR_DIA_CHUVA_MM).sum()) if not diario.empty else 0,
        "chuva_max_diaria": _max_com_momento(diario, "chuva_mm", "dia"),
        "intensidade_max": _max_com_momento(df15, "intensidade_mm_h"),
        "temp_media_c": _num(df15["temp_c"].mean()) if not df15.empty else None,
        "temp_max": _max_com_momento(df15, "temp_max_c" if df15["temp_max_c"].notna().any() else "temp_c"),
        "temp_min": _min_com_momento(df15, "temp_min_c" if df15["temp_min_c"].notna().any() else "temp_c"),
        "ur_media_pct": _num(df15["ur_pct"].mean(), 1) if not df15.empty else None,
        "vento_medio_ms": _num(df15["vento_ms"].mean()) if not df15.empty else None,
        "rajada_max": _max_com_momento(df15, "vento_max_ms"),
        "vento_max_15min": _max_com_momento(df15, "vento_ms"),
        "rad_media_mj_m2_dia": _num(diario["rad_mj_m2"].mean()) if not diario.empty else None,
        "variaveis": variaveis_com_dados(df15),
    }


# ---------------------------------------------------------------------------
# Série para gráficos
# ---------------------------------------------------------------------------

PASSOS = {"15min", "1h", "1D", "1W", "1M"}


def escolher_passo(inicio: date, fim: date) -> str:
    dias = (fim - inicio).days + 1
    if dias <= 4:
        return "15min"
    if dias <= 45:
        return "1h"
    if dias <= 800:
        return "1D"
    if dias <= 3660:
        return "1W"
    return "1M"


def serie(df15: pd.DataFrame, diario: pd.DataFrame, passo: str) -> pd.DataFrame:
    """Tabela regular no passo pedido (o rótulo é o fim do intervalo)."""
    if passo == "15min":
        s = df15[["data_hora", "chuva_mm", "intensidade_mm_h", "temp_c", "ur_pct",
                  "vento_ms", "vento_max_ms", "rad_w_m2", "pressao_hpa"]].copy()
        s = s.rename(columns={"data_hora": "t", "intensidade_mm_h": "intensidade_max_mm_h"})
        s["temp_max_c"] = df15["temp_max_c"]
        s["temp_min_c"] = df15["temp_min_c"]
    elif passo == "1h":
        base = df15.set_index("data_hora")
        r = base.resample("1h", label="right", closed="right")
        s = pd.DataFrame({
            "chuva_mm": r["chuva_mm"].sum(min_count=1),
            "intensidade_max_mm_h": r["intensidade_mm_h"].max(),
            "temp_c": r["temp_c"].mean(),
            "temp_max_c": r["temp_max_c"].max().fillna(r["temp_c"].max()),
            "temp_min_c": r["temp_min_c"].min().fillna(r["temp_c"].min()),
            "ur_pct": r["ur_pct"].mean(),
            "vento_ms": r["vento_ms"].mean(),
            "vento_max_ms": r["vento_max_ms"].max(),
            "rad_w_m2": r["rad_w_m2"].mean(),
            "pressao_hpa": r["pressao_hpa"].mean(),
        })
        s.index.name = "t"
        s = s.reset_index()
    else:
        d = diario.set_index("dia")
        if passo == "1D":
            s = d.drop(columns=["registros", "cobertura_pct"]).copy()
        else:
            regra = "W-SUN" if passo == "1W" else "MS"
            r = d.resample(regra, label="left" if passo == "1M" else "right", closed="right" if passo == "1W" else "left")
            s = pd.DataFrame({
                "chuva_mm": r["chuva_mm"].sum(min_count=1),
                "intensidade_max_mm_h": r["intensidade_max_mm_h"].max(),
                "temp_c": r["temp_c"].mean(),
                "temp_max_c": r["temp_max_c"].mean(),
                "temp_min_c": r["temp_min_c"].mean(),
                "ur_pct": r["ur_pct"].mean(),
                "vento_ms": r["vento_ms"].mean(),
                "vento_max_ms": r["vento_max_ms"].max(),
                "rad_mj_m2": r["rad_mj_m2"].mean(),
                "pressao_hpa": r["pressao_hpa"].mean(),
            })
        s.index.name = "t"
        s = s.reset_index()

    s["chuva_acum_mm"] = s["chuva_mm"].fillna(0).cumsum().where(s["chuva_mm"].notna().cumsum() > 0)
    return s


def serie_para_json(s: pd.DataFrame) -> dict:
    """Formato colunar ({coluna: [valores]}) – menor e direto para o ECharts."""
    saida = {"t": [pd.Timestamp(t).isoformat() for t in s["t"]]}
    for c in s.columns:
        if c == "t":
            continue
        if s[c].notna().any():
            vals = s[c].astype(float).round(3)
            saida[c] = [None if (v is None or np.isnan(v)) else float(v) for v in vals.tolist()]
    return saida


# ---------------------------------------------------------------------------
# Relatórios (diário, semanal, mensal, anual)
# ---------------------------------------------------------------------------

ESCALAS = {"diario": None, "semanal": "W-SUN", "mensal": "M", "anual": "Y"}


def _rotulo(periodo: pd.Period, escala: str) -> str:
    if escala == "semanal":
        ini, fim = periodo.start_time, periodo.end_time
        return f"{ini:%d/%m} – {fim:%d/%m/%Y}"
    if escala == "mensal":
        return f"{MESES[periodo.month - 1]}/{periodo.year}"
    if escala == "anual":
        return str(periodo.year)
    return f"{periodo.start_time:%d/%m/%Y}"


def relatorio(diario: pd.DataFrame, df15: pd.DataFrame, escala: str) -> pd.DataFrame:
    """Tabela agregada por dia/semana/mês/ano."""
    if escala not in ESCALAS:
        raise ValueError(f"Escala inválida: {escala}")
    if diario.empty:
        return pd.DataFrame()

    d = diario.copy()
    if escala == "diario":
        tab = d.rename(columns={"dia": "inicio"})
        tab["fim"] = tab["inicio"]
        tab["periodo"] = tab["inicio"].dt.strftime("%d/%m/%Y")
        if not df15.empty and df15["intensidade_mm_h"].notna().any():
            idx = df15.dropna(subset=["intensidade_mm_h"]).groupby("dia")["intensidade_mm_h"].idxmax()
            momentos = df15.loc[idx, ["dia", "data_hora"]].set_index("dia")["data_hora"]
            tab["momento_intensidade_max"] = tab["inicio"].map(momentos)
        else:
            tab["momento_intensidade_max"] = pd.NaT
        ordem = ["periodo", "inicio", "fim", "chuva_mm", "intensidade_max_mm_h", "momento_intensidade_max",
                 "temp_c", "temp_max_c", "temp_min_c", "ur_pct", "vento_ms", "vento_max_ms",
                 "rad_mj_m2", "pressao_hpa", "cobertura_pct"]
        return tab[ordem].reset_index(drop=True)

    freq = ESCALAS[escala]
    d["per"] = d["dia"].dt.to_period(freq)
    g = d.groupby("per")

    tab = pd.DataFrame({
        "chuva_mm": g["chuva_mm"].sum(min_count=1),
        "dias_chuva": g["chuva_mm"].apply(lambda x: int((x >= LIMIAR_DIA_CHUVA_MM).sum())),
        "chuva_max_diaria_mm": g["chuva_mm"].max(),
        "intensidade_max_mm_h": g["intensidade_max_mm_h"].max(),
        "temp_c": g["temp_c"].mean(),
        "temp_max_c": g["temp_max_c"].max(),
        "temp_min_c": g["temp_min_c"].min(),
        "temp_max_media_c": g["temp_max_c"].mean(),
        "temp_min_media_c": g["temp_min_c"].mean(),
        "ur_pct": g["ur_pct"].mean(),
        "vento_ms": g["vento_ms"].mean(),
        "vento_max_ms": g["vento_max_ms"].max(),
        "rad_mj_m2": g["rad_mj_m2"].mean(),
        "pressao_hpa": g["pressao_hpa"].mean(),
        "dias_com_dados": g["chuva_mm"].count(),
        "cobertura_pct": g["cobertura_pct"].mean(),
    })

    # Dia da chuva máxima e momento da intensidade máxima
    validos = d.dropna(subset=["chuva_mm"])
    if not validos.empty:
        idx = validos.groupby("per")["chuva_mm"].idxmax()
        tab["data_chuva_max_diaria"] = pd.Series(validos.loc[idx, "dia"].values, index=validos.loc[idx, "per"].values)
    else:
        tab["data_chuva_max_diaria"] = pd.NaT

    if not df15.empty and df15["intensidade_mm_h"].notna().any():
        x = df15.dropna(subset=["intensidade_mm_h"])[["dia", "data_hora", "intensidade_mm_h"]].copy()
        x["per"] = x["dia"].dt.to_period(freq)
        idx = x.groupby("per")["intensidade_mm_h"].idxmax()
        tab["momento_intensidade_max"] = pd.Series(x.loc[idx, "data_hora"].values, index=x.loc[idx, "per"].values)
    else:
        tab["momento_intensidade_max"] = pd.NaT

    tab.index.name = "per"
    tab = tab.reset_index()
    tab["inicio"] = tab["per"].apply(lambda p: p.start_time.normalize())
    tab["fim"] = tab["per"].apply(lambda p: p.end_time.normalize())
    tab["periodo"] = tab["per"].apply(lambda p: _rotulo(p, escala))
    ordem = ["periodo", "inicio", "fim", "chuva_mm", "dias_chuva", "chuva_max_diaria_mm", "data_chuva_max_diaria",
             "intensidade_max_mm_h", "momento_intensidade_max", "temp_c", "temp_max_c", "temp_min_c",
             "temp_max_media_c", "temp_min_media_c", "ur_pct", "vento_ms", "vento_max_ms", "rad_mj_m2",
             "pressao_hpa", "dias_com_dados", "cobertura_pct"]
    return tab[ordem]


def tabela_para_json(tab: pd.DataFrame) -> list[dict]:
    """Converte DataFrame em lista de dicionários (datas ISO, NaN -> None)."""
    registros = []
    for linha in tab.to_dict(orient="records"):
        item = {}
        for k, v in linha.items():
            if v is None or v is pd.NaT:
                item[k] = None
            elif isinstance(v, pd.Timestamp):
                item[k] = v.isoformat()
            elif isinstance(v, pd.Period):
                item[k] = str(v)
            elif isinstance(v, (bool, np.bool_)):
                item[k] = bool(v)
            elif isinstance(v, (float, np.floating)):
                item[k] = None if np.isnan(v) else round(float(v), 3)
            elif isinstance(v, np.integer):
                item[k] = int(v)
            else:
                item[k] = v
        registros.append(item)
    return registros
