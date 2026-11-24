"""Leitura e normalização dos arquivos da estação automática da ESALQ.

Os arquivos `diarioAAAA.xls` do LEB seguem o formato TOA5 dos dataloggers
Campbell: algumas linhas de cabeçalho, uma linha com os nomes das colunas
(TIMESTAMP, RECORD, ...), uma linha de unidades ("TS", "RN", "mm", "m/s", ...)
e, às vezes, uma linha de tipo de processamento ("Avg", "Tot", "Smp").

Como os nomes das colunas variam com o programa do datalogger ao longo dos
anos, a identificação das variáveis é feita por palavras-chave + unidades.
O que foi encontrado em cada arquivo fica registrado em `info["mapeamento"]`
(e em `dados/esalq/colunas.json` pelo script de atualização), para conferência.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import datetime
from datetime import time as dt_time
from typing import Any

import numpy as np
import pandas as pd

from .config import COLUNAS_15MIN

# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------


def _norm(texto: Any) -> str:
    """Remove acentos, deixa minúsculo e troca separadores por "_"."""
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower())
    return s.strip("_")


def _tokens(texto: Any) -> list[str]:
    return [t for t in _norm(texto).split("_") if t]


def _tem(tokens: list[str], *alvos: str, prefixo: bool = True) -> bool:
    """True se algum token é (ou começa com) um dos alvos."""
    for t in tokens:
        for a in alvos:
            if t == a or (prefixo and t.startswith(a)):
                return True
    return False


# ---------------------------------------------------------------------------
# Leitura do arquivo bruto
# ---------------------------------------------------------------------------


def _ler_tabela_bruta(conteudo: bytes) -> pd.DataFrame:
    """Lê xls/xlsx/csv/html sem cabeçalho (todas as células como objetos)."""
    inicio = conteudo[:8]
    erros = []

    # XLS (OLE2) ou XLSX (zip)
    if inicio.startswith(b"\xd0\xcf\x11\xe0") or inicio.startswith(b"PK"):
        try:
            abas = pd.read_excel(io.BytesIO(conteudo), header=None, dtype=object, sheet_name=None)
            abas = [a for a in abas.values() if not a.empty]
            if not abas:
                raise ValueError("planilha vazia")
            # Abas uma embaixo da outra (cada uma com o seu cabeçalho, se tiver)
            return pd.concat(abas, ignore_index=True) if len(abas) > 1 else abas[0]
        except Exception as exc:  # noqa: BLE001
            erros.append(f"excel: {exc}")

    texto = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if texto is not None:
        if "<table" in texto.lower():
            try:
                tabelas = pd.read_html(io.StringIO(texto), header=None)
                if tabelas:
                    return max(tabelas, key=len).astype(object)
            except Exception as exc:  # noqa: BLE001
                erros.append(f"html: {exc}")
        # CSV / DAT (TOA5 em texto). A 1ª linha do TOA5 tem menos campos que as
        # demais, então o nº de colunas é definido pela linha mais longa.
        amostra = texto[:20000]
        sep = max([",", ";", "\t"], key=amostra.count)
        n_campos = max((len(next(csv.reader([ln], delimiter=sep))) for ln in amostra.splitlines()[:30] if ln), default=1)
        try:
            return pd.read_csv(
                io.StringIO(texto), header=None, names=list(range(n_campos)), sep=sep, dtype=object,
                engine="python", on_bad_lines="skip",
            )
        except Exception as exc:  # noqa: BLE001
            erros.append(f"csv: {exc}")

    raise ValueError("Formato de arquivo não reconhecido (" + "; ".join(erros) + ")")


# Nomes das colunas de tempo nos formatos antigos (Campbell CR10/CR10X e planilhas do LEB)
_NOMES_TEMPO = {
    "timestamp": ("timestamp", "data_hora", "datahora", "date_time", "datetime"),
    "data": ("data", "date"),
    "ano": ("ano", "year", "yr", "aaaa"),
    "mes": ("mes", "month", "mon"),
    "dia": ("dia", "day", "dj", "julian", "doy", "dia_jul", "diajul", "dia_juliano", "dia_do_ano",
            "jday", "julian_day", "dia_j", "d_jul", "djul"),
    "hora": ("hora", "time", "hhmm", "hour", "hr_min", "horario", "hora_min", "hm", "hrmin", "hora_local",
             "hh_mm", "hora_minuto", "horas"),
}


def _papel_tempo(nome: Any) -> str | None:
    """'timestamp', 'data', 'ano', 'mes', 'dia' ou 'hora' para colunas de tempo."""
    n = _norm(nome)
    if not n:
        return None
    if n.startswith("timestamp"):
        return "timestamp"
    for papel, nomes in _NOMES_TEMPO.items():
        if n in nomes:
            return papel
    if n.startswith(("dia_jul", "diajul", "julian")):
        return "dia"
    return None


def _eh_cabecalho(celulas: list) -> bool:
    """Linha de nomes de colunas: TIMESTAMP (TOA5) ou colunas de tempo dos formatos antigos.

    A linha de legenda ("Dia Jul = Dia juliano") não conta: o texto não é só o nome.
    """
    celulas = [v for v in celulas if pd.notna(v) and str(v).strip()]
    if any(_norm(v).startswith("timestamp") for v in celulas):
        return True
    papeis = {_papel_tempo(v) for v in celulas}
    return len(celulas) >= 3 and "hora" in papeis and bool(papeis & {"data", "dia"})


def _linhas_de_cabecalho(bruto: pd.DataFrame) -> list[int]:
    """Todas as linhas de cabeçalho do arquivo.

    Alguns arquivos têm mais de um bloco: o de 2016 traz o formato antigo até
    março e, depois da troca da estação, um bloco TOA5 com cabeçalho próprio.
    """
    if bruto.empty:
        return []
    nomes_tempo = {n for nomes in _NOMES_TEMPO.values() for n in nomes}
    candidatas = pd.Series(False, index=bruto.index)
    for c in bruto.columns[: min(4, bruto.shape[1])]:
        t = (
            bruto[c].astype(str).str.normalize("NFKD").str.encode("ascii", "ignore").str.decode("ascii")
            .str.lower().str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_")
        )
        candidatas |= t.str.startswith("timestamp") | t.isin(nomes_tempo) | t.str.startswith(("dia_jul", "julian"))
    return [int(i) for i in np.flatnonzero(candidatas.to_numpy()) if _eh_cabecalho(bruto.iloc[i].tolist())]


def _achar_linha_cabecalho(bruto: pd.DataFrame) -> int | None:
    linhas = _linhas_de_cabecalho(bruto)
    return linhas[0] if linhas else None


def _legenda(bruto: pd.DataFrame, ate: int) -> dict[str, tuple[str, str]]:
    """Legenda acima do cabeçalho ("UR = Umidade Relativa (%)") -> {sigla: (descrição, unidade)}."""
    saida: dict[str, tuple[str, str]] = {}
    for i in range(ate):
        for v in bruto.iloc[i].tolist():
            if not isinstance(v, str) or "=" not in v:
                continue
            for parte in re.split(r"[;\n]", v):
                m = re.match(r"\s*([^=]{1,25}?)\s*=\s*(.+?)\s*$", parte)
                if not m:
                    continue
                desc = m.group(2)
                unidades = re.findall(r"\(([^()]*)\)", desc)
                saida[_norm(m.group(1))] = (desc, unidades[-1] if unidades else "")
    return saida


def _nomes_unicos(nomes: list[Any]) -> list[str]:
    vistos: dict[str, int] = {}
    saida = []
    for n in nomes:
        base = str(n).strip() if n is not None and str(n) != "nan" else "col"
        if base in vistos:
            vistos[base] += 1
            saida.append(f"{base}__{vistos[base]}")
        else:
            vistos[base] = 0
            saida.append(base)
    return saida


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def _para_datetime(serie: pd.Series) -> pd.Series:
    """Converte strings/datas/seriais do Excel em datetime64 (sem fuso)."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie

    numerico = pd.to_numeric(serie, errors="coerce")
    if numerico.notna().mean() > 0.9 and numerico.between(20000, 80000).mean() > 0.9:
        # Serial de data do Excel
        return pd.to_datetime(numerico, unit="D", origin="1899-12-30").dt.round("s")

    texto = serie.astype(str).str.strip()
    dt = pd.to_datetime(texto, errors="coerce", format="ISO8601")
    if dt.notna().mean() < 0.9:
        dt2 = pd.to_datetime(texto, errors="coerce", format="mixed", dayfirst=True)
        if dt2.notna().sum() > dt.notna().sum():
            dt = dt2
    return dt


def _minutos_do_dia(serie: pd.Series) -> pd.Series:
    """Hora do registro em minutos desde 00:00.

    Aceita HHMM (Campbell: 15, 1230, 2400), horas inteiras (1–24), fração do
    dia do Excel (0,5 = 12:00), objetos de hora e texto "HH:MM".
    """
    objetos = serie.dropna()
    if len(objetos) and all(isinstance(v, (dt_time, datetime)) for v in objetos.head(50)):
        return serie.map(lambda v: v.hour * 60 + v.minute + v.second / 60 if isinstance(v, (dt_time, datetime)) else np.nan)

    num = pd.to_numeric(serie, errors="coerce")
    preenchidas = int((serie.notna() & (serie.astype(str).str.strip() != "")).sum())
    # Numérica se a maioria das células preenchidas for número (sobram linhas de texto
    # entre os blocos, como "Trocada a estação automática")
    if num.notna().any() and num.notna().sum() >= 0.5 * preenchidas:
        validos = num.dropna()
        if validos.max() <= 1.0001 and (validos % 1 != 0).any():
            return (num * 1440).round(3)
        if validos.max() <= 24 and (validos % 1 == 0).all():
            return num * 60
        return (num // 100) * 60 + num % 100

    texto = serie.astype(str).str.strip()
    partes = texto.str.extract(r"^(\d{1,2})[:h](\d{2})(?::(\d{2}))?")
    h = pd.to_numeric(partes[0], errors="coerce")
    m = pd.to_numeric(partes[1], errors="coerce")
    s = pd.to_numeric(partes[2], errors="coerce").fillna(0)
    return h * 60 + m + s / 60


def _timestamp_de_colunas(df: pd.DataFrame, ano_arquivo: int | None = None) -> pd.Series | None:
    """Monta o timestamp para formatos sem coluna TIMESTAMP."""
    cols: dict[str, str] = {}
    for c in df.columns:
        papel = _papel_tempo(c)
        if papel and papel not in cols:
            cols[papel] = c

    if "timestamp" in cols:
        return _para_datetime(df[cols["timestamp"]])
    if "hora" not in cols:
        return None
    minutos = pd.to_timedelta(_minutos_do_dia(df[cols["hora"]]), unit="min")

    if "data" in cols:
        data = _para_datetime(df[cols["data"]]).dt.normalize()
        return data + minutos

    if "dia" not in cols:
        return None
    dia = pd.to_numeric(df[cols["dia"]], errors="coerce")
    if "ano" in cols:
        ano = pd.to_numeric(df[cols["ano"]], errors="coerce")
        ano = ano.where(ano >= 100, ano + np.where(ano < 70, 2000, 1900))  # "05" -> 2005
    elif ano_arquivo is not None:
        # Sem coluna de ano: o dia juliano que volta de ~365 para 1 marca a virada do
        # ano (o arquivo de 2016 começa com o registro de 23:45 de 31/12/2015).
        virada = (dia.ffill().diff() < -300).cumsum()
        validos = virada[dia.notna()]
        mais_comum = int(validos.mode().iloc[0]) if len(validos) else 0
        ano = (ano_arquivo - mais_comum + virada).astype(float)
    else:
        return None
    ano_txt = ano.astype("Int64").astype(str)

    if "mes" in cols:  # ano + mês + dia do mês
        mes = pd.to_numeric(df[cols["mes"]], errors="coerce").astype("Int64").astype(str)
        data = pd.to_datetime(ano_txt + "-" + mes + "-" + dia.astype("Int64").astype(str), errors="coerce")
        return data + minutos
    # ano + dia juliano (+ hora). 2400 vira 00:00 do dia seguinte.
    base = pd.to_datetime(ano_txt + "-01-01", errors="coerce")
    return base + pd.to_timedelta(dia - 1, unit="D") + minutos


# ---------------------------------------------------------------------------
# Identificação das variáveis
# ---------------------------------------------------------------------------

_EXCLUI_TEMP = (
    "solo", "soil", "orv", "dew", "panel", "painel", "ptemp", "bat", "batt", "log",
    "ref", "interna", "intern", "globo", "agua", "water", "umido", "molhado", "wet",
    "tw", "tbu", "cabine", "caixa", "enclosure",
)
_EXCLUI_DP = ("std", "sd", "desv", "desvio", "sigma", "dp")


# Descrições da legenda que indicam outra grandeza (temperatura do bulbo úmido, do solo…)
_EXCLUI_DESCRICAO_TEMP = ("umido", "orvalho", "solo", "molhado", "globo", "agua", "painel", "interna")


def _classificar_coluna(nome: str, unidade: str, descricao: str = "") -> tuple[str | None, int]:
    """Retorna (variável normalizada, prioridade) para uma coluna bruta."""
    tk = _tokens(nome)
    un = _norm(unidade)
    ut = _tokens(unidade)
    desc = _norm(descricao)
    if not tk:
        return None, 0
    junto = "".join(tk)

    if junto in ("timestamp", "record", "rn", "ts") or tk[0] in ("record", "registro"):
        return None, 0
    # "Tempo" = duração, não temperatura
    if "tempo" in tk or "duracao" in tk:
        return None, 0

    eh_max = _tem(tk, "max", "maximo", "maxima") or junto.startswith(("tmax", "tx"))
    eh_min = _tem(tk, "min", "minimo", "minima") or junto.startswith(("tmin", "tn"))
    eh_dp = _tem(tk, *_EXCLUI_DP, prefixo=False) or any(t.startswith("sd") and t[2:].isdigit() for t in tk)

    # Chuva
    if _tem(tk, "chuva", "rain", "precip", "prec", "pluv", "ppt") and not _tem(tk, "int", "intens", "dur"):
        prioridade = 3 if _tem(tk, "tot", "mm", "total") else 2
        return "chuva_mm", prioridade

    # Direção do vento (antes da velocidade). Na ESALQ: Dvento_G, Dvento_D1_WVT; em 1997 a
    # coluna se chama só "Vento" e a unidade é "Dir(g)"
    if (_tem(tk, "dir", "wd", "direcao", "winddir") or _tem(tk, "dv", prefixo=False)
            or junto.startswith(("dvento", "dirvento", "ddv"))
            or (_tem(ut, "dir", prefixo=False) and ("vento" in junto or "wind" in junto))):
        if eh_dp:
            return None, 0
        # D1 do WindVector = direção média vetorial do intervalo (melhor que a instantânea)
        return "vento_dir_graus", 3 if _tem(tk, "d1", prefixo=False) else 2

    # Rajada
    if _tem(tk, "raj", "rajada", "gust"):
        return (None, 0) if eh_dp else ("vento_max_ms", 3)

    # Velocidade do vento. Na ESALQ: Vvento_ms_AVG, Vvento_ms_S_WVT
    if (_tem(tk, "vento", "wind", "ws", "vel", "velocidade", "windspd", "wspd", "anemo")
            or _tem(tk, "vv", "u2", prefixo=False)
            or "vento" in junto
            or junto.startswith("vv")):
        if eh_dp:
            return None, 0
        if eh_max:
            return "vento_max_ms", 2
        prioridade = 3 if _tem(tk, "avg", "med", "media", "mean", "s", "wvt") else 2
        return "vento_ms", prioridade

    # Umidade relativa
    if (_tem(tk, "ur", "rh", "umid", "umidade", "umrel", prefixo=False)
            or junto.startswith(("rh", "umid", "urel"))):
        if any(e in junto for e in ("solo", "soil", "folha", "leaf")) or eh_dp:
            return None, 0
        if eh_max or eh_min:
            return None, 0
        return "ur_pct", 3 if _tem(tk, "avg", "med", "media") else 2

    # Radiação solar global
    if _tem(tk, "rad", "rg", "radiacao", "slr", "solar", "piran", "qg", "rs", prefixo=False) or junto.startswith(("rad", "slr")):
        if (_tem(tk, "rn", "par", "ir", "dif")
                or any(e in junto for e in ("liq", "net", "uv", "refl", "difus", "albedo", "fotoss", "saldo", "longa", "atmosf"))
                or eh_dp):
            return None, 0
        if eh_max or eh_min:
            return None, 0
        return "rad_w_m2", 2

    # Pressão atmosférica (não a pressão de vapor: "es", "ea", "DPV" dos arquivos antigos)
    if _tem(tk, "press", "pressao", "bp", "patm", "pressure", "baro", "pa", prefixo=False) or junto.startswith(("press", "baro", "bp")):
        if eh_max or eh_min or eh_dp or any(e in junto + "_" + desc for e in ("satur", "vapor", "dpv", "deficit")):
            return None, 0
        return "pressao_hpa", 2

    # Temperatura do ar
    eh_temp = (
        _tem(tk, "temp", "tar", "airtc", "tair", "temperatura", "t", "tmed", "tmedia", "tmax", "tmin", prefixo=False)
        or junto.startswith(("temp", "tar", "airtc", "tair"))
        or junto in ("tmax", "tmin", "tmed", "tx", "tn")
        or un in ("deg_c", "c", "degc", "oc", "graus_c")
    )
    if eh_temp:
        if any(e in junto for e in _EXCLUI_TEMP) or eh_dp:
            return None, 0
        # "Tu" (bulbo úmido), "To"/"Td" (ponto de orvalho) e o que a legenda descrever como tal
        if junto in ("tu", "to", "td", "tpo", "tw") or any(e in desc for e in _EXCLUI_DESCRICAO_TEMP):
            return None, 0
        if eh_max:
            return "temp_max_c", 2
        if eh_min:
            return "temp_min_c", 2
        return "temp_c", 3 if _tem(tk, "avg", "med", "media", "mean") else 2

    return None, 0


def _fator_conversao(var: str, unidade: str, serie: pd.Series, dt_s: float) -> tuple[float | None, float, str]:
    """(multiplicador, deslocamento, descrição) para levar à unidade padrão."""
    un = _norm(unidade)
    if var.startswith("vento") and var != "vento_dir_graus":
        if "km" in un:
            return 1 / 3.6, 0.0, "km/h → m/s"
        if un.startswith(("mph", "mi_", "miles")):
            return 0.44704, 0.0, "mph → m/s"
        return 1.0, 0.0, "m/s"
    if var == "rad_w_m2":
        if un.startswith("kw"):
            return 1000.0, 0.0, "kW/m² → W/m²"
        if "mj" in un:
            return 1e6 / dt_s, 0.0, "MJ/m² por intervalo → W/m²"
        if "kj" in un:
            return 1e3 / dt_s, 0.0, "kJ/m² por intervalo → W/m²"
        if "w" in un:
            return 1.0, 0.0, "W/m²"
        maximo = pd.to_numeric(serie, errors="coerce").quantile(0.99)
        if pd.notna(maximo) and maximo < 2.5:
            return 1000.0, 0.0, "kW/m² (inferido) → W/m²"
        return 1.0, 0.0, "W/m² (suposto)"
    if var == "pressao_hpa":
        if "kpa" in un:
            return 10.0, 0.0, "kPa → hPa"
        if "mmhg" in un:
            return 1.33322, 0.0, "mmHg → hPa"
        mediana = pd.to_numeric(serie, errors="coerce").median()
        if pd.notna(mediana) and mediana < 200:
            return 10.0, 0.0, "kPa (inferido) → hPa"
        return 1.0, 0.0, "hPa"
    if var.startswith("temp"):
        if un in ("deg_f", "f", "degf"):
            return 5 / 9, -32 * 5 / 9, "°F → °C"
        return 1.0, 0.0, "°C"
    return 1.0, 0.0, ""


# ---------------------------------------------------------------------------
# Limpeza
# ---------------------------------------------------------------------------

_SENTINELAS = [6999, 7999, 9999, -6999, -7999, -9999, 99999, -99999]

_FAIXAS = {
    "temp_c": (-10, 50),
    "temp_max_c": (-10, 50),
    "temp_min_c": (-10, 50),
    "ur_pct": (0, 105),
    "vento_ms": (0, 75),
    "vento_max_ms": (0, 90),
    "vento_dir_graus": (0, 360),
    "rad_w_m2": (-50, 1600),
    "pressao_hpa": (600, 1100),
}


def limpar_chuva(chuva: pd.Series) -> pd.Series:
    """Mesmos critérios do sistema original (valores de erro do sensor e picos isolados)."""
    c = pd.to_numeric(chuva, errors="coerce").astype(float)
    c = c.mask(c.isin([6999, 7999, 9999]))
    c = c.mask(c < 0)
    c = c.mask(c > 150)
    anterior = c.shift(1)
    seguinte = c.shift(-1)
    pico_isolado = (c > 100) & (anterior < 1) & (seguinte < 1)
    return c.mask(pico_isolado)


def limpar_variavel(var: str, serie: pd.Series) -> pd.Series:
    s = pd.to_numeric(serie, errors="coerce").astype(float)
    s = s.mask(s.isin(_SENTINELAS))
    if var in _FAIXAS:
        lo, hi = _FAIXAS[var]
        s = s.mask((s < lo) | (s > hi))
    if var == "ur_pct":
        s = s.clip(upper=100)
    if var == "rad_w_m2":
        s = s.clip(lower=0)
    return s


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------


def _eh_linha_de_texto(linha: pd.Series) -> bool:
    """Linha de unidades/tipo logo abaixo do cabeçalho (quase tudo texto, nada de números)."""
    celulas = [v for v in linha.tolist() if pd.notna(v) and str(v).strip()]
    if len(celulas) < 2:
        return False
    numeros = pd.to_numeric(pd.Series(celulas, dtype=object).astype(str).str.replace(",", "."), errors="coerce")
    return numeros.notna().mean() < 0.2


def _ler_bloco(bloco: pd.DataFrame, legenda: dict, ano_arquivo: int | None) -> tuple[pd.DataFrame, dict]:
    """Lê um bloco de dados (a 1ª linha é o cabeçalho)."""
    nomes = _nomes_unicos(bloco.iloc[0].tolist())
    corpo = bloco.iloc[1:].reset_index(drop=True)
    corpo.columns = nomes

    # Linha de unidades logo após o cabeçalho (TOA5: "TS" na coluna TIMESTAMP; antigos: "oC", "W/m2"…)
    unidades = {n: "" for n in nomes}
    if len(corpo) > 0 and _eh_linha_de_texto(corpo.iloc[0]):
        unidades = {n: ("" if pd.isna(corpo.at[0, n]) else str(corpo.at[0, n]).strip()) for n in nomes}
        corpo = corpo.iloc[1:].reset_index(drop=True)
    # Formatos antigos: descrição (e unidade) na legenda acima do cabeçalho ("UR = Umidade Relativa (%)")
    descricoes: dict[str, str] = {}
    for n in nomes:
        item = legenda.get(_norm(n))
        if item:
            descricoes[n] = item[0]
            if not unidades.get(n):
                unidades[n] = item[1]

    data_hora = _timestamp_de_colunas(corpo, ano_arquivo)
    if data_hora is None:
        raise ValueError("não foi possível montar a data/hora dos registros")

    corpo = corpo.assign(_dh=data_hora).dropna(subset=["_dh"])
    corpo = corpo.sort_values("_dh").drop_duplicates("_dh", keep="last").reset_index(drop=True)
    if corpo.empty:
        raise ValueError("nenhum registro com data/hora válida")

    dt_s = corpo["_dh"].diff().dt.total_seconds().mode()
    dt_s = float(dt_s.iloc[0]) if len(dt_s) and dt_s.iloc[0] > 0 else 900.0

    # Classifica as colunas e escolhe a de maior prioridade para cada variável
    candidatos: dict[str, tuple[int, str]] = {}
    for n in nomes:
        if n == "_dh" or _papel_tempo(n):
            continue
        var, prioridade = _classificar_coluna(n, unidades.get(n, ""), descricoes.get(n, ""))
        if var is None and n in descricoes:
            # Sigla desconhecida: tenta pela descrição da legenda (prioridade menor)
            var, prioridade = _classificar_coluna(descricoes[n], unidades.get(n, ""), descricoes[n])
            prioridade -= 1
        if var is None:
            continue
        valores = pd.to_numeric(corpo[n], errors="coerce")
        if valores.notna().sum() == 0:
            continue
        atual = candidatos.get(var)
        if atual is None or prioridade > atual[0]:
            candidatos[var] = (prioridade, n)

    saida = pd.DataFrame({"data_hora": corpo["_dh"].values})
    mapeamento: dict[str, str] = {}
    conversoes: dict[str, str] = {}
    for var in COLUNAS_15MIN[1:]:
        if var not in candidatos:
            saida[var] = np.nan
            continue
        coluna = candidatos[var][1]
        mapeamento[var] = coluna
        valores = pd.to_numeric(corpo[coluna], errors="coerce")
        if var == "chuva_mm":
            saida[var] = limpar_chuva(valores).values
            continue
        mult, desloc, desc = _fator_conversao(var, unidades.get(coluna, ""), valores, dt_s)
        valores = valores.mask(valores.isin(_SENTINELAS))
        valores = valores * mult + desloc
        conversoes[var] = desc
        saida[var] = limpar_variavel(var, valores).values

    info = {
        "colunas_brutas": [n for n in nomes if n != "_dh" and not n.startswith("col")],
        "unidades": {k: v for k, v in unidades.items() if v},
        "legenda": descricoes,
        "mapeamento": mapeamento,
        "conversoes": conversoes,
        "intervalo_s": dt_s,
        "registros": int(len(saida)),
        "inicio": saida["data_hora"].min().isoformat(),
        "fim": saida["data_hora"].max().isoformat(),
    }
    return saida, info


def ler_arquivo_esalq(conteudo: bytes, ano_arquivo: int | None = None) -> tuple[pd.DataFrame, dict]:
    """Lê o arquivo da estação e devolve (dados normalizados, info).

    O DataFrame tem as colunas de `config.COLUNAS_15MIN` (as que não existirem
    no arquivo ficam vazias). `ano_arquivo` só é usado se o arquivo não tiver
    a coluna do ano (formatos antigos com dia juliano + hora).

    Um arquivo pode ter vários blocos, cada um com o seu cabeçalho (o de 2016
    muda do formato antigo para o TOA5 quando a estação foi trocada).
    """
    bruto = _ler_tabela_bruta(conteudo)
    cabecalhos = _linhas_de_cabecalho(bruto)
    if not cabecalhos:
        raise ValueError("Cabeçalho não encontrado (nem TIMESTAMP, nem colunas de data/dia e hora)")
    legenda = _legenda(bruto, cabecalhos[0])

    partes, infos, erros = [], [], []
    for k, ini in enumerate(cabecalhos):
        fim = cabecalhos[k + 1] if k + 1 < len(cabecalhos) else len(bruto)
        try:
            df_b, info_b = _ler_bloco(bruto.iloc[ini:fim].reset_index(drop=True), legenda, ano_arquivo)
        except ValueError as exc:
            erros.append(f"bloco da linha {ini + 1}: {exc}")
            continue
        info_b["linha_cabecalho"] = ini + 1
        partes.append(df_b)
        infos.append(info_b)
    if not partes:
        raise ValueError("; ".join(erros))

    df = pd.concat(partes, ignore_index=True) if len(partes) > 1 else partes[0]
    df = df.sort_values("data_hora").drop_duplicates("data_hora", keep="last").reset_index(drop=True)

    # O bloco com mais registros descreve o arquivo; as variáveis encontradas são a soma dos blocos
    principal = max(infos, key=lambda i: i["registros"])
    mapeamento: dict[str, str] = {}
    for i in sorted(infos, key=lambda i: i["registros"]):
        mapeamento.update(i["mapeamento"])
    info = {
        **principal,
        "mapeamento": {v: mapeamento[v] for v in COLUNAS_15MIN[1:] if v in mapeamento},
        "registros": int(len(df)),
        "inicio": df["data_hora"].min().isoformat(),
        "fim": df["data_hora"].max().isoformat(),
    }
    if len(infos) > 1:
        info["blocos"] = [
            {k: i[k] for k in ("linha_cabecalho", "registros", "inicio", "fim", "intervalo_s", "mapeamento")}
            for i in infos
        ]
    if erros:
        info["avisos"] = erros
    return df, info


# ---------------------------------------------------------------------------
# Derivados usados nas análises
# ---------------------------------------------------------------------------


def dia_meteorologico(data_hora: pd.Series) -> pd.Series:
    """Dia a que pertence cada registro.

    O TIMESTAMP dos dataloggers marca o FIM do intervalo: o registro de 00:00
    corresponde a 23:45–00:00 do dia anterior.
    """
    return (data_hora - pd.Timedelta(seconds=1)).dt.normalize()


# Maior intervalo entre registros aceito como "passo" da série (h). Acima disso
# os dados são diários ou há falhas longas.
INTERVALO_MAX_H = 3.0


def intervalo_nominal(data_hora: pd.Series, dia: pd.Series | None = None) -> pd.Series:
    """Intervalo de registro (h) de cada linha: o intervalo mais comum do seu dia.

    Usa o passo do dia, e não a diferença até o registro anterior, porque depois
    de uma falha o registro continua valendo só pelo seu intervalo (15 min, 1 h).
    Assim séries que mudam de resolução ao longo dos anos (horária → 15 min)
    também ficam certas.
    """
    if data_hora.empty:
        return pd.Series(dtype="float64", index=data_hora.index)
    if dia is None:
        dia = dia_meteorologico(data_hora)
    dif = (data_hora.diff().dt.total_seconds() / 3600).round(4)
    ok = (dif > 0) & (dif <= INTERVALO_MAX_H)
    if not ok.any():
        return pd.Series(np.nan, index=data_hora.index)
    contagem = pd.DataFrame({"dia": dia[ok], "dif": dif[ok]}).groupby(["dia", "dif"]).size()
    modal_dia = contagem.groupby(level=0).idxmax().map(lambda t: t[1])
    modal_geral = float(dif[ok].mode().iloc[0])
    return dia.map(modal_dia).astype("float64").fillna(modal_geral)


def adicionar_derivados(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta intervalo (h), intensidade (mm/h), dia e chuva acumulada no dia."""
    df = df.sort_values("data_hora").reset_index(drop=True)
    dia = dia_meteorologico(df["data_hora"])
    intervalo = intervalo_nominal(df["data_hora"], dia)

    intensidade = df["chuva_mm"] / intervalo
    intensidade = intensidade.mask(intensidade > 500)

    df = df.assign(intervalo_h=intervalo, intensidade_mm_h=intensidade, dia=dia)
    df["chuva_acum_dia_mm"] = df.groupby("dia")["chuva_mm"].cumsum()
    return df
