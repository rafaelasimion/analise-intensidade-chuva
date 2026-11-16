"""Estações automáticas do INMET em SP: catálogo, leitura dos CSVs e dados diários.

Os dados históricos vêm dos pacotes anuais abertos do INMET
(https://portal.inmet.gov.br/dadoshistoricos), que não exigem token.
O script `scripts/atualizar_dados.py` baixa os pacotes, extrai as estações
de SP, agrega por dia e grava `dados/inmet/diario/inmet_sp_AAAA.csv.gz`.
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
import zipfile
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DIR_INMET, DIR_INMET_DIARIO

ARQ_ESTACOES = DIR_INMET / "estacoes_sp.json"

COLUNAS_DIARIO = [
    "codigo", "dia", "chuva_mm", "temp_c", "temp_max_c", "temp_min_c", "ur_pct",
    "vento_ms", "vento_max_ms", "rad_mj_m2", "pressao_hpa", "horas",
]

MIN_HORAS_DIA = 18


def _norm(texto) -> str:
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


# O INMET publica os nomes em maiúsculas e sem acento ("SAO PAULO - MIRANTE")
_ACENTOS = {
    "SAO": "São", "JORDAO": "Jordão", "AVARE": "Avaré", "BRAGANCA": "Bragança", "JOSE": "José",
    "BONIFACIO": "Bonifácio", "MARILIA": "Marília", "PRADOPOLIS": "Pradópolis", "SEBASTIAO": "Sebastião",
    "SIMAO": "Simão", "TAUBATE": "Taubaté", "TUPA": "Tupã", "VALPARAISO": "Valparaíso", "LUIS": "Luiz",
    "JOAO": "João", "MOGI": "Mogi", "GUARA": "Guará", "ITAI": "Itaí", "PIRAJU": "Piraju",
}
_MINUSCULAS = {"DO", "DA", "DE", "DOS", "DAS", "E"}


def nome_legivel(nome: str) -> str:
    """'CAMPOS DO JORDAO' -> 'Campos do Jordão'; 'SAO PAULO - MIRANTE' -> 'São Paulo – Mirante'."""
    if not nome or not nome.isupper():
        return nome
    palavras = []
    for i, p in enumerate(nome.replace(" - ", " – ").split()):
        if p in _ACENTOS:
            palavras.append(_ACENTOS[p])
        elif p in _MINUSCULAS and i > 0:
            palavras.append(p.lower())
        else:
            palavras.append(p.capitalize())
    return " ".join(palavras)


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------


def estacoes() -> list[dict]:
    if not ARQ_ESTACOES.exists():
        return []
    try:
        dados = json.loads(ARQ_ESTACOES.read_text("utf-8"))
    except (ValueError, OSError):
        return []
    return dados.get("estacoes", []) if isinstance(dados, dict) else dados


def estacao(codigo: str) -> dict | None:
    codigo = codigo.upper()
    return next((e for e in estacoes() if e["codigo"].upper() == codigo), None)


def salvar_estacoes(lista: list[dict], fonte: str) -> None:
    ARQ_ESTACOES.parent.mkdir(parents=True, exist_ok=True)
    lista = sorted(lista, key=lambda e: e["nome"])
    ARQ_ESTACOES.write_text(
        json.dumps({"fonte": fonte, "estacoes": lista}, ensure_ascii=False, indent=1), "utf-8"
    )


# ---------------------------------------------------------------------------
# Leitura de um CSV horário do INMET
# ---------------------------------------------------------------------------

_MAPA = [
    ("chuva_mm", ("precipitacao_total",)),
    ("temp_c", ("bulbo_seco",)),
    ("temp_max_c", ("temperatura_maxima_na_hora",)),
    ("temp_min_c", ("temperatura_minima_na_hora",)),
    ("ur_pct", ("umidade_relativa_do_ar",)),
    ("vento_ms", ("vento_velocidade",)),
    ("vento_max_ms", ("vento_rajada",)),
    ("rad_kj_m2", ("radiacao_global",)),
    ("pressao_hpa", ("pressao_atmosferica_ao_nivel_da_estacao",)),
]


def _numero(serie: pd.Series) -> pd.Series:
    s = serie.astype(str).str.strip().str.replace(",", ".", regex=False)
    v = pd.to_numeric(s, errors="coerce")
    return v.mask(v <= -9999 + 1e-6)


def ler_csv_inmet(conteudo: bytes) -> tuple[dict, pd.DataFrame]:
    """(metadados, dados horários com data_hora em hora local de Brasília)."""
    texto = conteudo.decode("latin-1")
    linhas = texto.splitlines()

    meta: dict = {}
    for linha in linhas[:8]:
        if ";" not in linha:
            continue
        chave, valor = linha.split(";", 1)
        chave = _norm(chave)
        valor = valor.strip().strip(";").strip()
        if chave.startswith("regi"):
            meta["regiao"] = valor
        elif chave == "uf":
            meta["uf"] = valor
        elif chave.startswith("estac"):
            meta["nome"] = valor
        elif chave.startswith("codigo"):
            meta["codigo"] = valor.upper()
        elif chave.startswith("latitude"):
            meta["lat"] = float(valor.replace(",", "."))
        elif chave.startswith("longitude"):
            meta["lon"] = float(valor.replace(",", "."))
        elif chave.startswith("altitude"):
            meta["alt"] = float(valor.replace(",", "."))
        elif chave.startswith("data_de_fundacao"):
            v = valor
            if re.fullmatch(r"\d{2}/\d{2}/\d{2}", v):
                dd, mm, aa = v.split("/")
                v = f"20{aa}-{mm}-{dd}"
            elif re.fullmatch(r"\d{2}/\d{2}/\d{4}", v):
                dd, mm, aaaa = v.split("/")
                v = f"{aaaa}-{mm}-{dd}"
            meta["fundacao"] = v

    df = pd.read_csv(io.StringIO("\n".join(linhas[8:])), sep=";", dtype=str)
    cols = {c: _norm(c) for c in df.columns}
    col_data = df.columns[0]
    col_hora = df.columns[1]

    data = df[col_data].astype(str).str.strip().str.replace("/", "-", regex=False)
    hora = df[col_hora].astype(str).str.strip().str.replace(" UTC", "", regex=False)
    hora = hora.where(hora.str.contains(":"), hora.str.zfill(4).str[:2] + ":" + hora.str.zfill(4).str[2:])
    utc = pd.to_datetime(data + " " + hora, errors="coerce", format="%Y-%m-%d %H:%M")

    saida = pd.DataFrame({"data_hora": utc - pd.Timedelta(hours=3)})
    for destino, chaves in _MAPA:
        col = next((c for c, n in cols.items() if any(k in n for k in chaves)), None)
        saida[destino] = _numero(df[col]) if col is not None else np.nan

    saida = saida.dropna(subset=["data_hora"])
    # Faixas físicas
    saida["chuva_mm"] = saida["chuva_mm"].mask((saida["chuva_mm"] < 0) | (saida["chuva_mm"] > 150))
    for c in ("temp_c", "temp_max_c", "temp_min_c"):
        saida[c] = saida[c].mask((saida[c] < -10) | (saida[c] > 50))
    saida["ur_pct"] = saida["ur_pct"].mask((saida["ur_pct"] < 0) | (saida["ur_pct"] > 100))
    saida["vento_ms"] = saida["vento_ms"].mask((saida["vento_ms"] < 0) | (saida["vento_ms"] > 75))
    saida["vento_max_ms"] = saida["vento_max_ms"].mask((saida["vento_max_ms"] < 0) | (saida["vento_max_ms"] > 90))
    saida["pressao_hpa"] = saida["pressao_hpa"].mask((saida["pressao_hpa"] < 600) | (saida["pressao_hpa"] > 1100))
    return meta, saida


def diario_inmet(horario: pd.DataFrame) -> pd.DataFrame:
    """Agrega os dados horários por dia local (rótulo = fim da hora)."""
    if horario.empty:
        return pd.DataFrame(columns=COLUNAS_DIARIO[1:])
    h = horario.copy()
    h["dia"] = (h["data_hora"] - pd.Timedelta(seconds=1)).dt.normalize()
    g = h.groupby("dia")
    n_chuva = g["chuva_mm"].count()
    n_temp = g["temp_c"].count()
    ok_c = n_chuva >= MIN_HORAS_DIA
    ok_t = n_temp >= MIN_HORAS_DIA
    rad = g["rad_kj_m2"].apply(lambda x: x.clip(lower=0).sum() / 1000 if x.count() >= 10 else np.nan)
    d = pd.DataFrame({
        "chuva_mm": g["chuva_mm"].sum(min_count=1).where(ok_c),
        "temp_c": g["temp_c"].mean().where(ok_t),
        "temp_max_c": g["temp_max_c"].max().fillna(g["temp_c"].max()).where(ok_t),
        "temp_min_c": g["temp_min_c"].min().fillna(g["temp_c"].min()).where(ok_t),
        "ur_pct": g["ur_pct"].mean().where(g["ur_pct"].count() >= MIN_HORAS_DIA),
        "vento_ms": g["vento_ms"].mean().where(g["vento_ms"].count() >= MIN_HORAS_DIA),
        "vento_max_ms": g["vento_max_ms"].max(),
        "rad_mj_m2": rad,
        "pressao_hpa": g["pressao_hpa"].mean(),
        "horas": n_chuva.combine(n_temp, max),
    })
    d.index.name = "dia"
    return d.reset_index()


def processar_zip(caminho_zip: Path, uf: str = "SP") -> tuple[pd.DataFrame, list[dict]]:
    """Lê o pacote anual do INMET e devolve (diário de todas as estações da UF, metadados)."""
    partes, metas = [], []
    marcador = f"_{uf.upper()}_"
    with zipfile.ZipFile(caminho_zip) as z:
        for nome in z.namelist():
            base = Path(nome).name.upper()
            if not base.endswith(".CSV") or marcador not in base:
                continue
            meta, horario = ler_csv_inmet(z.read(nome))
            if not meta.get("codigo"):
                continue
            if meta.get("uf", uf).upper() != uf.upper():
                continue
            diario = diario_inmet(horario)
            if diario.empty:
                continue
            diario.insert(0, "codigo", meta["codigo"])
            partes.append(diario)
            metas.append(meta)
    if not partes:
        return pd.DataFrame(columns=COLUNAS_DIARIO), metas
    tudo = pd.concat(partes, ignore_index=True)
    tudo = tudo.drop_duplicates(["codigo", "dia"], keep="last").sort_values(["codigo", "dia"])
    return tudo[COLUNAS_DIARIO], metas


# ---------------------------------------------------------------------------
# Leitura dos arquivos diários do repositório
# ---------------------------------------------------------------------------


def caminho_ano(ano: int) -> Path:
    return DIR_INMET_DIARIO / f"inmet_sp_{ano}.csv.gz"


def anos_disponiveis() -> list[int]:
    return sorted(int(p.name.split("_")[2].split(".")[0]) for p in DIR_INMET_DIARIO.glob("inmet_sp_*.csv.gz"))


@lru_cache(maxsize=48)
def _ler_ano(ano: int, _mtime: float) -> pd.DataFrame:
    df = pd.read_csv(caminho_ano(ano), parse_dates=["dia"], dtype={"codigo": str})
    return df


def carregar_diario(codigo: str, inicio: date | None = None, fim: date | None = None) -> pd.DataFrame:
    codigo = codigo.upper()
    partes = []
    for ano in anos_disponiveis():
        if inicio and ano < inicio.year:
            continue
        if fim and ano > fim.year:
            continue
        p = caminho_ano(ano)
        df = _ler_ano(ano, p.stat().st_mtime)
        df = df[df["codigo"].str.upper() == codigo]
        if not df.empty:
            partes.append(df)
    if not partes:
        return pd.DataFrame(columns=COLUNAS_DIARIO)
    d = pd.concat(partes, ignore_index=True).sort_values("dia")
    if inicio:
        d = d[d["dia"] >= pd.Timestamp(inicio)]
    if fim:
        d = d[d["dia"] <= pd.Timestamp(fim)]
    return d.reset_index(drop=True)
