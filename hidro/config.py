"""Configurações gerais: caminhos, metadados das estações e constantes."""

from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

# Raiz do projeto (a Vercel executa as funções com a raiz como diretório de trabalho)
RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ / "dados"
DIR_ESALQ = DIR_DADOS / "esalq"
DIR_INMET = DIR_DADOS / "inmet"
DIR_INMET_DIARIO = DIR_INMET / "diario"

# Na Vercel só /tmp é gravável
DIR_TMP = Path(os.environ.get("HIDRO_TMP", "/tmp/hidro"))

# Fuso de Piracicaba / SP (hora padrão de Brasília, sem horário de verão desde 2019)
FUSO_BR = timezone(timedelta(hours=-3))

# ---------------------------------------------------------------------------
# Estação automática da ESALQ (LEB)
# ---------------------------------------------------------------------------
ESALQ = {
    "id": "esalq",
    "nome": "ESALQ/USP – Estação Automática (LEB)",
    "municipio": "Piracicaba",
    "uf": "SP",
    # Coordenadas do Posto Agrometeorológico da ESALQ (22°42'30" S, 47°38'00" W, 546 m).
    # Confirme com o LEB se a estação automática estiver em outro ponto do campus.
    "lat": -22.7083,
    "lon": -47.6333,
    "alt": 546.0,
    "rede": "ESALQ/USP",
    "fonte": "https://www.esalq.usp.br/departamentos/leb/automatica/pagina6.html",
}

# Os arquivos saíram do domínio antigo (www.leb.esalq.usp.br) e passaram para o
# domínio principal da ESALQ. O endereço antigo fica como reserva.
URLS_ESALQ = [
    "https://www.esalq.usp.br/departamentos/leb/automatica/diario{ano}.xls",
    "http://www.leb.esalq.usp.br/leb/automatica/diario{ano}.xls",
]
URL_ESALQ = URLS_ESALQ[0]

# Primeiro ano procurado pelo script de atualização (anos inexistentes são ignorados)
ANO_INICIAL_BUSCA_ESALQ = int(os.environ.get("ESALQ_ANO_INICIAL", "1997"))

# Tempo de cache do ano corrente baixado ao vivo (segundos)
TTL_ANO_ATUAL = int(os.environ.get("ESALQ_TTL", "3600"))

# ---------------------------------------------------------------------------
# INMET (estações automáticas)
# ---------------------------------------------------------------------------
URL_INMET_ANUAL = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"
ANO_INICIAL_INMET = 2000

# ---------------------------------------------------------------------------
# NASA POWER (estimativas por satélite/reanálise, usadas só quando escolhidas)
# ---------------------------------------------------------------------------
URL_NASA_POWER = "https://power.larc.nasa.gov/api/temporal/daily/point"

# ---------------------------------------------------------------------------
# Variáveis normalizadas da estação (dados de 15 min)
# ---------------------------------------------------------------------------
# id -> (rótulo, unidade, como agregar)
VARIAVEIS = {
    "chuva_mm": ("Chuva", "mm", "soma"),
    "intensidade_mm_h": ("Intensidade da chuva", "mm/h", "max"),
    "temp_c": ("Temperatura do ar", "°C", "media"),
    "temp_max_c": ("Temperatura máxima", "°C", "max"),
    "temp_min_c": ("Temperatura mínima", "°C", "min"),
    "ur_pct": ("Umidade relativa", "%", "media"),
    "vento_ms": ("Velocidade do vento", "m/s", "media"),
    "vento_max_ms": ("Rajada máxima", "m/s", "max"),
    "vento_dir_graus": ("Direção do vento", "°", "media_circular"),
    "rad_w_m2": ("Radiação solar global", "W/m²", "media"),
    "pressao_hpa": ("Pressão atmosférica", "hPa", "media"),
}

COLUNAS_15MIN = [
    "data_hora",
    "chuva_mm",
    "temp_c",
    "temp_max_c",
    "temp_min_c",
    "ur_pct",
    "vento_ms",
    "vento_max_ms",
    "vento_dir_graus",
    "rad_w_m2",
    "pressao_hpa",
]

# Limite usado para "dia com chuva" (padrão OMM)
LIMIAR_DIA_CHUVA_MM = 1.0
