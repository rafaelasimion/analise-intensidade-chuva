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

from .config import COLUNAS_15MIN, DIR_INMET, DIR_INMET_DIARIO, DIR_INMET_HORARIO, LIMITES_SP

ARQ_ESTACOES = DIR_INMET / "estacoes_sp.json"

# Dados horários guardados por estação e ano: dados/inmet/horario/<CODIGO>/<ANO>.csv.gz
# (o ano é o do dia meteorológico: o registro de 00:00 de 1º/jan fica no ano anterior)
COLUNAS_HORARIO = COLUNAS_15MIN
CASAS_HORARIO = {
    "chuva_mm": 1, "temp_c": 1, "temp_max_c": 1, "temp_min_c": 1, "ur_pct": 0, "vento_ms": 1,
    "vento_max_ms": 1, "vento_dir_graus": 0, "rad_w_m2": 0, "pressao_hpa": 1,
}
GZIP = {"method": "gzip", "compresslevel": 9, "mtime": 0}

# Horas (rótulo = fim da hora, hora local) sempre sem sol em SP; o INMET deixa a radiação em branco
HORAS_NOITE = (20, 21, 22, 23, 0, 1, 2, 3, 4, 5)
HORAS_CENTRAIS = range(8, 18)  # rótulos 08:00–17:00

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
    "JOAO": "João", "MOGI": "Mogi", "GUARA": "Guará", "ITAI": "Itaí", "PIRAJU": "Piraju", "IPERO": "Iperó",
    "JUNDIAI": "Jundiaí", "ARACATUBA": "Araçatuba", "GUARATINGUETA": "Guaratinguetá", "AGUAS": "Águas",
    "LINDOIA": "Lindóia", "GUAIRA": "Guaíra", "RIBEIRAO": "Ribeirão", "CANANEIA": "Cananéia", "GUACU": "Guaçu",
    "TATUI": "Tatuí", "CAPAO": "Capão", "BONITO": "Bonito", "ITAPECERICA": "Itapecerica", "IBIUNA": "Ibiúna",
    "JAU": "Jaú", "SERTAOZINHO": "Sertãozinho", "PARAISO": "Paraíso", "ITAPOLIS": "Itápolis", "MAUA": "Mauá",
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
    lista = dados.get("estacoes", []) if isinstance(dados, dict) else dados
    return [e for e in lista if dentro_de_sp(e.get("lat"), e.get("lon"))]


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
    ("vento_dir_graus", ("vento_direcao",)),
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
    saida["vento_dir_graus"] = saida["vento_dir_graus"].mask((saida["vento_dir_graus"] < 0) | (saida["vento_dir_graus"] > 360))
    # Radiação: kJ/m² na hora -> média em W/m² (÷ 3,6); valores negativos pequenos = 0
    rad = saida.pop("rad_kj_m2")
    saida["rad_w_m2"] = (rad.mask(rad > 5000).clip(lower=0) / 3.6)
    saida = saida.drop_duplicates("data_hora", keep="last").sort_values("data_hora").reset_index(drop=True)
    return meta, _completar_noite(saida)[COLUNAS_HORARIO]


def _dia(data_hora: pd.Series) -> pd.Series:
    """Dia meteorológico (o registro de 00:00 pertence ao dia anterior)."""
    return (data_hora - pd.Timedelta(seconds=1)).dt.normalize()


def _completar_noite(h: pd.DataFrame) -> pd.DataFrame:
    """Radiação em branco à noite vira 0 nos dias em que o sensor funcionou."""
    if h.empty:
        return h
    hora = h["data_hora"].dt.hour
    dia = _dia(h["data_hora"])
    centrais = h["rad_w_m2"].notna() & hora.isin(HORAS_CENTRAIS)
    ok = centrais.groupby(dia).transform("sum") >= 6
    noite = hora.isin(HORAS_NOITE) & h["rad_w_m2"].isna() & ok
    h = h.copy()
    h.loc[noite, "rad_w_m2"] = 0.0
    return h


def diario_inmet(horario: pd.DataFrame) -> pd.DataFrame:
    """Agrega os dados horários por dia local (rótulo = fim da hora)."""
    if horario.empty:
        return pd.DataFrame(columns=COLUNAS_DIARIO[1:])
    h = horario.copy()
    h["dia"] = _dia(h["data_hora"])
    g = h.groupby("dia")
    n_chuva = g["chuva_mm"].count()
    n_temp = g["temp_c"].count()
    ok_c = n_chuva >= MIN_HORAS_DIA
    ok_t = n_temp >= MIN_HORAS_DIA
    # Radiação do dia (MJ/m²): soma das horas (W/m² × 3600 s), se as horas centrais estiverem completas
    centrais = h["rad_w_m2"].where(h["data_hora"].dt.hour.isin(HORAS_CENTRAIS))
    ok_r = centrais.groupby(h["dia"]).count() >= 9
    rad = (g["rad_w_m2"].sum(min_count=1) * 0.0036).where(ok_r)
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


def estacoes_do_zip(caminho_zip: Path, uf: str = "SP"):
    """Percorre o pacote anual do INMET: (metadados, dados horários) de cada estação da UF."""
    marcador = f"_{uf.upper()}_"
    with zipfile.ZipFile(caminho_zip) as z:
        for nome in z.namelist():
            base = Path(nome).name.upper()
            if not base.endswith(".CSV") or marcador not in base:
                continue
            meta, horario = ler_csv_inmet(z.read(nome))
            if not meta.get("codigo") or meta.get("uf", uf).upper() != uf.upper():
                continue
            if not dentro_de_sp(meta.get("lat"), meta.get("lon")):
                continue
            yield meta, horario


def dentro_de_sp(lat, lon) -> bool:
    try:
        return (LIMITES_SP["lat"][0] <= float(lat) <= LIMITES_SP["lat"][1]
                and LIMITES_SP["lon"][0] <= float(lon) <= LIMITES_SP["lon"][1])
    except (TypeError, ValueError):
        return False


def processar_zip(caminho_zip: Path, uf: str = "SP") -> tuple[pd.DataFrame, list[dict]]:
    """Lê o pacote anual do INMET e devolve (diário de todas as estações da UF, metadados)."""
    partes, metas = [], []
    for meta, horario in estacoes_do_zip(caminho_zip, uf):
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
    d = pd.concat(partes, ignore_index=True)
    # 31/dez pode aparecer em dois arquivos (as últimas horas vêm no pacote do ano seguinte)
    d = d.assign(_n=d[["chuva_mm", "temp_c"]].notna().sum(axis=1) * 100 + d["horas"].fillna(0))
    d = d.sort_values(["dia", "_n"]).drop_duplicates("dia", keep="last").drop(columns="_n")
    if inicio:
        d = d[d["dia"] >= pd.Timestamp(inicio)]
    if fim:
        d = d[d["dia"] <= pd.Timestamp(fim)]
    return d.reset_index(drop=True)


def diario_todas(inicio: date, fim: date) -> pd.DataFrame:
    """Dados diários de todas as estações no intervalo (para o mapa)."""
    partes = []
    for ano in anos_disponiveis():
        if ano < inicio.year or ano > fim.year:
            continue
        p = caminho_ano(ano)
        df = _ler_ano(ano, p.stat().st_mtime)
        df = df[(df["dia"] >= pd.Timestamp(inicio)) & (df["dia"] <= pd.Timestamp(fim))]
        if not df.empty:
            partes.append(df)
    if not partes:
        return pd.DataFrame(columns=COLUNAS_DIARIO)
    d = pd.concat(partes, ignore_index=True)
    d = d.assign(_n=d[["chuva_mm", "temp_c"]].notna().sum(axis=1) * 100 + d["horas"].fillna(0))
    return d.sort_values(["codigo", "dia", "_n"]).drop_duplicates(["codigo", "dia"], keep="last").drop(columns="_n")


# ---------------------------------------------------------------------------
# Dados horários de cada estação
# ---------------------------------------------------------------------------


def caminho_horario(codigo: str, ano: int) -> Path:
    return DIR_INMET_HORARIO / codigo.upper() / f"{ano}.csv.gz"


def anos_horario(codigo: str) -> list[int]:
    pasta = DIR_INMET_HORARIO / codigo.upper()
    if not pasta.is_dir():
        return []
    return sorted(int(p.name.split(".")[0]) for p in pasta.glob("*.csv.gz") if p.name.split(".")[0].isdigit())


def _padronizar_horario(df: pd.DataFrame) -> pd.DataFrame:
    for c in COLUNAS_HORARIO:
        if c not in df.columns:
            df[c] = np.nan
    df = df[COLUNAS_HORARIO].copy()
    df["data_hora"] = pd.to_datetime(df["data_hora"], errors="coerce")
    for c in COLUNAS_HORARIO[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return df.dropna(subset=["data_hora"])


@lru_cache(maxsize=96)
def _ler_horario(codigo: str, ano: int, _mtime: float) -> pd.DataFrame:
    return _padronizar_horario(pd.read_csv(caminho_horario(codigo, ano)))


def ler_horario_ano(codigo: str, ano: int) -> pd.DataFrame:
    p = caminho_horario(codigo, ano)
    if not p.exists():
        return _padronizar_horario(pd.DataFrame(columns=COLUNAS_HORARIO))
    return _ler_horario(codigo.upper(), ano, p.stat().st_mtime)


def carregar_horario(codigo: str, inicio: date, fim: date) -> pd.DataFrame:
    """Registros horários cujo dia (fim da hora) está em [inicio, fim]."""
    anos = [a for a in anos_horario(codigo) if inicio.year <= a <= fim.year]
    partes = [ler_horario_ano(codigo, a) for a in anos]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return _padronizar_horario(pd.DataFrame(columns=COLUNAS_HORARIO))
    df = pd.concat(partes, ignore_index=True) if len(partes) > 1 else partes[0]
    dia = _dia(df["data_hora"])
    return df[(dia >= pd.Timestamp(inicio)) & (dia <= pd.Timestamp(fim))].reset_index(drop=True)


def limites_horario(codigo: str) -> dict:
    anos = anos_horario(codigo)
    if not anos:
        return {"inicio": None, "fim": None}
    primeiro, ultimo = ler_horario_ano(codigo, anos[0]), ler_horario_ano(codigo, anos[-1])
    return {
        "inicio": primeiro["data_hora"].min().isoformat() if not primeiro.empty else None,
        "fim": ultimo["data_hora"].max().isoformat() if not ultimo.empty else None,
    }


def gravar_horario(codigo: str, horario: pd.DataFrame) -> set[int]:
    """Junta os registros novos aos arquivos da estação (os novos têm prioridade). Devolve os anos alterados."""
    if horario.empty:
        return set()
    novo = _padronizar_horario(horario.copy())
    valores = COLUNAS_HORARIO[1:]
    novo = novo.dropna(subset=valores, how="all")
    anos = set()
    for ano, parte in novo.groupby(_dia(novo["data_hora"]).dt.year):
        destino = caminho_horario(codigo, int(ano))
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            antigo = _padronizar_horario(pd.read_csv(destino))
            parte = pd.concat([antigo, parte], ignore_index=True).drop_duplicates("data_hora", keep="last")
        parte = parte.sort_values("data_hora").round(CASAS_HORARIO)
        parte.to_csv(destino, index=False, float_format="%.6g", date_format="%Y-%m-%d %H:%M", compression=GZIP)
        anos.add(int(ano))
    return anos


def reconstruir_diario_ano(ano: int) -> pd.DataFrame:
    """Refaz dados/inmet/diario/inmet_sp_<ano>.csv.gz a partir dos arquivos horários."""
    partes = []
    if DIR_INMET_HORARIO.is_dir():
        for pasta in sorted(p for p in DIR_INMET_HORARIO.iterdir() if p.is_dir()):
            arq = pasta / f"{ano}.csv.gz"
            if not arq.exists():
                continue
            d = diario_inmet(_padronizar_horario(pd.read_csv(arq)))
            d = d[d["dia"].dt.year == ano]
            if d.empty:
                continue
            d.insert(0, "codigo", pasta.name)
            partes.append(d)
    if not partes:
        return pd.DataFrame(columns=COLUNAS_DIARIO)
    tudo = pd.concat(partes, ignore_index=True)
    # Dias que só existem no arquivo diário anterior (estação/ano ainda sem horário) continuam lá
    destino = caminho_ano(ano)
    if destino.exists():
        antigo = pd.read_csv(destino, parse_dates=["dia"], dtype={"codigo": str})
        tudo = pd.concat([antigo, tudo], ignore_index=True).drop_duplicates(["codigo", "dia"], keep="last")
    tudo = tudo.sort_values(["codigo", "dia"])[COLUNAS_DIARIO]
    DIR_INMET_DIARIO.mkdir(parents=True, exist_ok=True)
    tudo.to_csv(destino, index=False, float_format="%.4g", date_format="%Y-%m-%d", compression=GZIP)
    return tudo
