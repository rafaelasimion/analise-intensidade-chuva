"""Escolha da fonte de dados diários para o balanço hídrico e lista de postos."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import armazenamento, inmet, nasa_power
from .config import ESALQ

NASA_INICIO = date(1981, 1, 1)


def lista_postos(busca: str = "") -> list[dict]:
    """ESALQ + estações automáticas do INMET em SP (com o período de dados disponível)."""
    limites = armazenamento.limites_dados()
    postos = [{
        "id": "esalq",
        "fonte": "esalq",
        "codigo": "ESALQ",
        "nome": ESALQ["nome"],
        "municipio": ESALQ["municipio"],
        "uf": "SP",
        "lat": ESALQ["lat"],
        "lon": ESALQ["lon"],
        "alt": ESALQ["alt"],
        "rede": ESALQ["rede"],
        "tipo": "Automática (15 min)",
        "inicio_dados": (limites["inicio"] or "")[:10] or None,
        "fim_dados": (limites["fim"] or "")[:10] or None,
        "tem_dados": limites["inicio"] is not None,
    }]
    for e in inmet.estacoes():
        postos.append({
            "id": f"inmet-{e['codigo']}",
            "fonte": "inmet",
            "codigo": e["codigo"],
            "nome": inmet.nome_legivel(e["nome"]),
            "municipio": e.get("municipio") or inmet.nome_legivel(e["nome"].split(" - ")[0]),
            "uf": e.get("uf", "SP"),
            "lat": e["lat"],
            "lon": e["lon"],
            "alt": e.get("alt"),
            "rede": "INMET",
            "tipo": "Automática (horária)",
            "fundacao": e.get("fundacao"),
            "inicio_dados": e.get("inicio_dados"),
            "fim_dados": e.get("fim_dados"),
            "tem_dados": bool(e.get("inicio_dados")),
        })
    if busca:
        b = busca.strip().lower()
        postos = [p for p in postos if b in p["nome"].lower() or b in p["codigo"].lower()
                  or b in (p.get("municipio") or "").lower()]
    return postos


def dados_para_balanco(
    fonte: str, inicio: date, fim: date, codigo: str | None = None,
    lat: float | None = None, lon: float | None = None,
) -> tuple[pd.DataFrame, dict]:
    """(série diária com dia/chuva_mm/temp_c, informações do posto)."""
    fonte = fonte.lower()
    if fonte == "esalq":
        diario = armazenamento.carregar_diario_esalq()
        info = {"fonte": "esalq", "codigo": "ESALQ", "nome": ESALQ["nome"], "lat": ESALQ["lat"],
                "lon": ESALQ["lon"], "alt": ESALQ["alt"], "descricao_fonte": "Estação automática ESALQ/USP (LEB)"}
        if diario["temp_c"].notna().sum() == 0:
            raise ValueError(
                "Os dados da ESALQ salvos no repositório ainda não têm temperatura (só chuva). "
                "Rode o script de atualização (scripts/atualizar_dados.py) para baixar os arquivos completos, "
                "ou use a fonte NASA POWER para as coordenadas da ESALQ."
            )
        return diario, info

    if fonte == "inmet":
        if not codigo:
            raise ValueError("Informe o código da estação do INMET (ex.: A726)")
        est = inmet.estacao(codigo)
        if est is None:
            raise ValueError(f"Estação {codigo} não encontrada na lista de SP")
        diario = inmet.carregar_diario(codigo)
        info = {"fonte": "inmet", "codigo": est["codigo"], "nome": inmet.nome_legivel(est["nome"]), "lat": est["lat"],
                "lon": est["lon"], "alt": est.get("alt"), "descricao_fonte": "INMET – estação automática"}
        if diario.empty:
            raise ValueError(
                f"Ainda não há dados diários da estação {codigo} no repositório. "
                "Rode o script de atualização (atualizar_dados.py inmet) ou use a fonte NASA POWER."
            )
        return diario, info

    if fonte == "nasa":
        nome = "Coordenada informada"
        alt = None
        if codigo and codigo.upper() == "ESALQ":
            lat, lon, nome, alt = ESALQ["lat"], ESALQ["lon"], ESALQ["nome"], ESALQ["alt"]
        elif codigo:
            est = inmet.estacao(codigo)
            if est is None:
                raise ValueError(f"Estação {codigo} não encontrada")
            lat, lon, nome, alt = est["lat"], est["lon"], inmet.nome_legivel(est["nome"]), est.get("alt")
        if lat is None or lon is None:
            raise ValueError("Informe latitude e longitude (ou um posto)")
        # Baixa também anos anteriores ao período, para as normais
        ini = max(NASA_INICIO, min(inicio, date(fim.year - 10, 1, 1)))
        fi = min(fim, date.today() - timedelta(days=5))
        if fi <= ini:
            raise ValueError("Período sem dados no NASA POWER")
        diario = nasa_power.carregar_diario(lat, lon, ini, fi)
        info = {"fonte": "nasa", "codigo": (codigo or "").upper() or None, "nome": nome, "lat": lat, "lon": lon,
                "alt": alt, "descricao_fonte": "NASA POWER (estimativa por satélite/reanálise, grade ~0,5°)"}
        return diario, info

    raise ValueError("Fonte inválida (use esalq, inmet ou nasa)")
