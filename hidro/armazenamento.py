"""Acesso aos dados da ESALQ: arquivos do repositório + ano corrente ao vivo.

- Anos anteriores: `dados/esalq/esalq_AAAA.csv.gz` (gerados por
  `scripts/atualizar_dados.py`, que roda toda semana no GitHub Actions).
- Ano corrente: baixado do site do LEB na hora (com cache em memória de
  1 h); se o site estiver fora do ar, usa a cópia do repositório.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

from .config import COLUNAS_15MIN, DIR_ESALQ, FUSO_BR, TTL_ANO_ATUAL, URLS_ESALQ
from .esalq import adicionar_derivados, ler_arquivo_esalq

ARQ_ANOS = DIR_ESALQ / "anos.json"
ARQ_COLUNAS = DIR_ESALQ / "colunas.json"

_cache_vivo: dict[int, dict] = {}
_travas: dict[int, threading.Lock] = {}
_trava_global = threading.Lock()

# Se o download falhar, espera este tempo antes de tentar de novo (s)
_ESPERA_APOS_FALHA = 600


def caminho_ano(ano: int) -> Path:
    return DIR_ESALQ / f"esalq_{ano}.csv.gz"


def hoje() -> date:
    return datetime.now(FUSO_BR).date()


def anos_ao_vivo() -> set[int]:
    """Anos que ainda recebem dados (o anterior também, na 1ª semana do ano)."""
    h = hoje()
    anos = {h.year}
    if h.timetuple().tm_yday <= 7:
        anos.add(h.year - 1)
    return anos


def anos_disponiveis() -> list[int]:
    anos = {int(p.stem.split("_")[1].split(".")[0]) for p in DIR_ESALQ.glob("esalq_*.csv.gz")}
    if ARQ_ANOS.exists():
        try:
            anos |= set(json.loads(ARQ_ANOS.read_text("utf-8")).get("disponiveis", []))
        except (ValueError, OSError):
            pass
    anos |= anos_ao_vivo()
    return sorted(anos)


def info_colunas() -> dict:
    if ARQ_COLUNAS.exists():
        try:
            return json.loads(ARQ_COLUNAS.read_text("utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _vazio() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="float64") for c in COLUNAS_15MIN})
    df["data_hora"] = pd.Series(dtype="datetime64[ns]")
    return df


def _padronizar(df: pd.DataFrame) -> pd.DataFrame:
    for c in COLUNAS_15MIN:
        if c not in df.columns:
            df[c] = float("nan")
    df = df[COLUNAS_15MIN].copy()
    df["data_hora"] = pd.to_datetime(df["data_hora"], errors="coerce")
    for c in COLUNAS_15MIN[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return df.dropna(subset=["data_hora"])


@lru_cache(maxsize=64)
def _ler_ano_repositorio(ano: int, _mtime: float) -> pd.DataFrame:
    caminho = caminho_ano(ano)
    if not caminho.exists():
        return _vazio()
    return _padronizar(pd.read_csv(caminho, parse_dates=["data_hora"]))


def ler_ano_repositorio(ano: int) -> pd.DataFrame:
    caminho = caminho_ano(ano)
    mtime = caminho.stat().st_mtime if caminho.exists() else 0.0
    return _ler_ano_repositorio(ano, mtime)


def baixar_ano(ano: int, timeout: tuple[float, float] = (6, 30)) -> tuple[pd.DataFrame, dict]:
    """Baixa e normaliza o arquivo de um ano do site da ESALQ (endereço novo; o antigo é reserva)."""
    falhas = []
    for modelo in URLS_ESALQ:
        url = modelo.format(ano=ano)
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (analise-chuva-esalq)"})
            resp.raise_for_status()
            df, info = ler_arquivo_esalq(resp.content)
        except Exception as exc:  # noqa: BLE001 - tenta o próximo endereço
            falhas.append(f"{url}: {type(exc).__name__}")
            continue
        info["url"] = url
        return df, info
    raise RuntimeError("; ".join(falhas))


def _trava(ano: int) -> threading.Lock:
    with _trava_global:
        return _travas.setdefault(ano, threading.Lock())


def carregar_ano(ano: int, atualizar: bool = False) -> tuple[pd.DataFrame, dict]:
    """Dados de 15 min de um ano + metadados da origem."""
    if ano not in anos_ao_vivo():
        df = ler_ano_repositorio(ano)
        return df, {"ano": ano, "origem": "repositorio", "registros": int(len(df))}

    agora = time.time()
    with _trava(ano):
        cache = _cache_vivo.get(ano)
        fresco = cache and cache.get("df") is not None and agora - cache["quando"] < TTL_ANO_ATUAL
        esperando = cache and cache.get("df") is None and agora - cache["quando"] < _ESPERA_APOS_FALHA
        if fresco and not atualizar:
            return cache["df"], cache["meta"]
        if esperando and not atualizar:
            df = ler_ano_repositorio(ano)
            return df, {**cache["meta"], "registros": int(len(df))}

        try:
            df_novo, info = baixar_ano(ano)
            df_repo = ler_ano_repositorio(ano)
            # Junta com o repositório (o site pode ter cortado registros antigos)
            df = pd.concat([df_repo, _padronizar(df_novo)], ignore_index=True)
            df = df.drop_duplicates("data_hora", keep="last").sort_values("data_hora")
            df = df[df["data_hora"].dt.year == ano].reset_index(drop=True)
            meta = {
                "ano": ano,
                "origem": "ao_vivo",
                "atualizado_em": datetime.now(FUSO_BR).isoformat(timespec="seconds"),
                "registros": int(len(df)),
                "mapeamento": info.get("mapeamento", {}),
            }
            _cache_vivo[ano] = {"quando": agora, "df": df, "meta": meta}
            return df, meta
        except Exception as exc:  # noqa: BLE001 - qualquer falha cai no repositório
            df = ler_ano_repositorio(ano)
            meta = {
                "ano": ano,
                "origem": "repositorio",
                "aviso": f"Não foi possível baixar {ano} do site da ESALQ ({type(exc).__name__}). "
                         "Usando a última cópia salva.",
                "registros": int(len(df)),
            }
            _cache_vivo[ano] = {"quando": agora, "df": None, "meta": meta}
            return df, meta


def carregar_15min(inicio: date, fim: date, atualizar: bool = False) -> tuple[pd.DataFrame, list[dict]]:
    """Registros de 15 min cujo dia (fim do intervalo) está em [inicio, fim]."""
    if fim < inicio:
        inicio, fim = fim, inicio
    # O registro 00:00 de 1º/jan pertence a 31/dez, por isso lê o ano seguinte também
    anos = range(inicio.year, (fim + timedelta(days=1)).year + 1)
    disponiveis = set(anos_disponiveis())
    partes, metas = [], []
    for ano in anos:
        if ano not in disponiveis:
            continue
        df, meta = carregar_ano(ano, atualizar=atualizar)
        if not df.empty:
            partes.append(df)
        metas.append(meta)
    if not partes:
        return adicionar_derivados(_vazio()), metas

    df = pd.concat(partes, ignore_index=True).drop_duplicates("data_hora", keep="last")
    df = adicionar_derivados(df)
    mascara = (df["dia"] >= pd.Timestamp(inicio)) & (df["dia"] <= pd.Timestamp(fim))
    return df.loc[mascara].reset_index(drop=True), metas


@lru_cache(maxsize=64)
def _diario_ano_repositorio(ano: int, _mtime: float, _mtime_prox: float) -> pd.DataFrame:
    from .agregacao import diario_de_15min

    df = ler_ano_repositorio(ano)
    prox = ler_ano_repositorio(ano + 1)
    virada = pd.Timestamp(f"{ano + 1}-01-01 00:00:00")
    df = pd.concat([df, prox[prox["data_hora"] <= virada]], ignore_index=True)
    if df.empty:
        return diario_de_15min(adicionar_derivados(_vazio()))
    d = diario_de_15min(adicionar_derivados(df.drop_duplicates("data_hora", keep="last")))
    return d[d["dia"].dt.year == ano].reset_index(drop=True)


def carregar_diario_esalq(inicio: date | None = None, fim: date | None = None) -> pd.DataFrame:
    """Série diária da ESALQ (anos antigos ficam em cache; o ano corrente é recalculado)."""
    from .agregacao import diario_de_15min

    anos = anos_disponiveis()
    if not anos:
        return diario_de_15min(adicionar_derivados(_vazio()))
    ini = inicio or date(anos[0], 1, 1)
    fi = fim or hoje()
    partes = []
    vivos = anos_ao_vivo()
    for ano in range(ini.year, fi.year + 1):
        if ano not in anos:
            continue
        if ano in vivos or (ano + 1) in vivos:
            df15, _ = carregar_15min(date(ano, 1, 1), date(ano, 12, 31))
            partes.append(diario_de_15min(df15))
        else:
            p1, p2 = caminho_ano(ano), caminho_ano(ano + 1)
            partes.append(_diario_ano_repositorio(
                ano, p1.stat().st_mtime if p1.exists() else 0.0, p2.stat().st_mtime if p2.exists() else 0.0
            ))
    if not partes:
        return diario_de_15min(adicionar_derivados(_vazio()))
    d = pd.concat([p for p in partes if not p.empty], ignore_index=True) if any(not p.empty for p in partes) else partes[0]
    d = d.drop_duplicates("dia", keep="last").sort_values("dia")
    d = d[(d["dia"] >= pd.Timestamp(ini)) & (d["dia"] <= pd.Timestamp(fi))]
    return d.reset_index(drop=True)


def limites_dados() -> dict:
    """Primeiro e último registro disponíveis (sem baixar nada da internet)."""
    anos = [a for a in anos_disponiveis() if caminho_ano(a).exists()]
    if not anos:
        return {"inicio": None, "fim": None}
    primeiro = ler_ano_repositorio(anos[0])
    ultimo_ano = max(anos)
    ultimo = ler_ano_repositorio(ultimo_ano)
    cache = _cache_vivo.get(hoje().year)
    if cache and cache.get("df") is not None and not cache["df"].empty:
        ultimo = cache["df"]
    return {
        "inicio": primeiro["data_hora"].min().isoformat() if not primeiro.empty else None,
        "fim": ultimo["data_hora"].max().isoformat() if not ultimo.empty else None,
    }
