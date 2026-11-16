"""NASA POWER: chuva e temperatura diárias estimadas para qualquer coordenada.

Usado só como alternativa quando o posto não tem série observada suficiente.
São estimativas por satélite/reanálise (grade de ~0,5°), não medições do posto.
API aberta, sem chave: https://power.larc.nasa.gov/docs/services/api/
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd
import requests

from .config import URL_NASA_POWER

PARAMETROS = "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN"


@lru_cache(maxsize=32)
def _baixar(lat: float, lon: float, inicio: str, fim: str) -> pd.DataFrame:
    resp = requests.get(
        URL_NASA_POWER,
        params={
            "parameters": PARAMETROS,
            "community": "AG",
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "start": inicio,
            "end": fim,
            "format": "JSON",
        },
        timeout=(8, 50),
    )
    resp.raise_for_status()
    param = resp.json()["properties"]["parameter"]
    df = pd.DataFrame(param)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(-999.0, np.nan).astype(float)
    df = df.rename(columns={
        "PRECTOTCORR": "chuva_mm", "T2M": "temp_c", "T2M_MAX": "temp_max_c", "T2M_MIN": "temp_min_c",
    })
    df.index.name = "dia"
    return df.reset_index()


def carregar_diario(lat: float, lon: float, inicio: date, fim: date) -> pd.DataFrame:
    # Arredonda para aproveitar o cache entre pedidos parecidos
    return _baixar(round(lat, 3), round(lon, 3), inicio.strftime("%Y%m%d"), fim.strftime("%Y%m%d")).copy()
