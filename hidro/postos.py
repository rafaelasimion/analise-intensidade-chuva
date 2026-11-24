"""Postos meteorológicos: um acesso só para a ESALQ (15 min) e as estações do INMET (horárias).

Cada posto tem um id usado nas rotas da API e nos endereços do site:
"esalq" ou "inmet-<código>" (p.ex. "inmet-A711").
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import armazenamento, inmet
from .config import ESALQ
from .esalq import adicionar_derivados

ID_ESALQ = "esalq"
PREFIXO_INMET = "inmet-"

COLUNAS_DIARIO = [
    "dia", "chuva_mm", "intensidade_max_mm_h", "temp_c", "temp_max_c", "temp_min_c",
    "ur_pct", "vento_ms", "vento_max_ms", "rad_mj_m2", "pressao_hpa", "registros", "cobertura_pct",
]


class PostoDesconhecido(LookupError):
    pass


def normalizar_id(pid: str) -> str:
    """'ESALQ' -> 'esalq'; 'A711', 'inmet-a711' -> 'inmet-A711'."""
    p = (pid or "").strip()
    if p.lower() == ID_ESALQ:
        return ID_ESALQ
    if p.lower().startswith(PREFIXO_INMET):
        p = p[len(PREFIXO_INMET):]
    return PREFIXO_INMET + p.upper()


def _info_esalq() -> dict:
    lim = armazenamento.limites_dados()
    return {
        "id": ID_ESALQ,
        "fonte": "esalq",
        "codigo": "ESALQ",
        "nome": ESALQ["nome"],
        "nome_curto": "ESALQ/USP",
        "municipio": ESALQ["municipio"],
        "uf": "SP",
        "lat": ESALQ["lat"],
        "lon": ESALQ["lon"],
        "alt": ESALQ["alt"],
        "rede": ESALQ["rede"],
        "tipo": "Automática (15 min)",
        "resolucao_min": 15,
        "inicio_dados": (lim["inicio"] or "")[:10] or None,
        "fim_dados": (lim["fim"] or "")[:10] or None,
        "tem_dados": lim["inicio"] is not None,
        "tem_registros": lim["inicio"] is not None,
        "ao_vivo": True,
        "url_fonte": ESALQ["fonte"],
    }


def _info_inmet(e: dict) -> dict:
    codigo = e["codigo"].upper()
    nome = inmet.nome_legivel(e["nome"])
    return {
        "id": PREFIXO_INMET + codigo,
        "fonte": "inmet",
        "codigo": codigo,
        "nome": nome,
        "nome_curto": nome,
        "municipio": e.get("municipio") or inmet.nome_legivel(e["nome"].split(" - ")[0]),
        "uf": "SP",
        "lat": e["lat"],
        "lon": e["lon"],
        "alt": e.get("alt"),
        "rede": "INMET",
        "tipo": "Automática (horária)",
        "resolucao_min": 60,
        "fundacao": e.get("fundacao"),
        "inicio_dados": e.get("inicio_dados"),
        "fim_dados": e.get("fim_dados"),
        "tem_dados": bool(e.get("inicio_dados")),
        "tem_registros": bool(inmet.anos_horario(codigo)),
        "ao_vivo": False,
        "url_fonte": "https://portal.inmet.gov.br/dadoshistoricos",
    }


def listar(busca: str = "") -> list[dict]:
    """ESALQ + estações automáticas do INMET em SP."""
    postos = [_info_esalq()] + [_info_inmet(e) for e in inmet.estacoes()]
    if busca:
        b = busca.strip().lower()
        postos = [p for p in postos if b in p["nome"].lower() or b in p["codigo"].lower()
                  or b in (p.get("municipio") or "").lower()]
    return postos


def obter(pid: str) -> dict:
    pid = normalizar_id(pid)
    if pid == ID_ESALQ:
        return _info_esalq()
    est = inmet.estacao(pid[len(PREFIXO_INMET):])
    if est is None:
        raise PostoDesconhecido(f"Posto '{pid}' não encontrado")
    return _info_inmet(est)


def limites(pid: str) -> dict:
    """Primeiro e último registro (ISO). Para o INMET sem dados horários, usa os diários."""
    pid = normalizar_id(pid)
    if pid == ID_ESALQ:
        return armazenamento.limites_dados()
    info = obter(pid)
    if info["tem_registros"]:
        return inmet.limites_horario(info["codigo"])
    if info["inicio_dados"]:
        # fim do dia: o último registro do dia D é D+1 00:00
        fim = pd.Timestamp(info["fim_dados"]) + pd.Timedelta(days=1)
        return {"inicio": pd.Timestamp(info["inicio_dados"]).isoformat(), "fim": fim.isoformat()}
    return {"inicio": None, "fim": None}


def anos(pid: str) -> list[int]:
    pid = normalizar_id(pid)
    if pid == ID_ESALQ:
        return armazenamento.anos_disponiveis()
    info = obter(pid)
    if info["tem_registros"]:
        return inmet.anos_horario(info["codigo"])
    if info["inicio_dados"] and info["fim_dados"]:
        return list(range(int(info["inicio_dados"][:4]), int(info["fim_dados"][:4]) + 1))
    return []


def carregar_registros(pid: str, inicio: date, fim: date, atualizar: bool = False) -> tuple[pd.DataFrame, list[dict]]:
    """Registros na resolução do posto (15 min ou 1 h), com intensidade e dia."""
    pid = normalizar_id(pid)
    if pid == ID_ESALQ:
        return armazenamento.carregar_15min(inicio, fim, atualizar=atualizar)
    info = obter(pid)
    h = inmet.carregar_horario(info["codigo"], inicio, fim)
    meta = {"origem": "repositorio", "fonte": "INMET (pacotes anuais)", "registros": int(len(h))}
    if not info["tem_registros"]:
        meta["aviso"] = ("Os dados horários desta estação ainda não foram processados; "
                         "por enquanto só os totais diários estão disponíveis.")
    return adicionar_derivados(h), [meta]


def diario_de_inmet(d: pd.DataFrame) -> pd.DataFrame:
    """Arquivo diário do INMET no mesmo formato do diário calculado dos registros."""
    if d.empty:
        return pd.DataFrame(columns=COLUNAS_DIARIO)
    saida = d.copy()
    saida["intensidade_max_mm_h"] = np.nan
    saida["registros"] = saida["horas"]
    saida["cobertura_pct"] = (saida["horas"] / 24 * 100).clip(upper=100)
    return saida[COLUNAS_DIARIO].reset_index(drop=True)


def carregar_diario(pid: str, inicio: date | None = None, fim: date | None = None) -> pd.DataFrame:
    """Série diária do posto (para o balanço hídrico, o mapa e a comparação)."""
    pid = normalizar_id(pid)
    if pid == ID_ESALQ:
        return armazenamento.carregar_diario_esalq(inicio, fim)
    info = obter(pid)
    return diario_de_inmet(inmet.carregar_diario(info["codigo"], inicio, fim))
