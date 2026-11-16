"""Balanço hídrico climatológico de Thornthwaite & Mather (1955).

Evapotranspiração potencial (ETP) por Thornthwaite (1948), como nas planilhas
de Rolim, Sentelhas & Barbieri (1998, ESALQ) e em Pereira, Angelocci &
Sentelhas (2002, "Agrometeorologia: fundamentos e aplicações práticas"):

    I  = Σ (0,2·Tn)^1,514                       (Tn = normais mensais, °C)
    a  = 6,75e-7·I³ − 7,71e-5·I² + 1,7912e-2·I + 0,49239
    ETp = 16·(10·T/I)^a                         0 < T < 26,5 °C
    ETp = −415,85 + 32,24·T − 0,43·T²           T ≥ 26,5 °C
    ETP = ETp · (N/12) · (NDP/30)               N = fotoperíodo, NDP = nº de dias

Balanço (CAD = capacidade de água disponível, mm):
    P − ETP < 0:  NEG.AC = NEG.AC(ant) + (P − ETP);  ARM = CAD·exp(NEG.AC/CAD)
    P − ETP ≥ 0:  ARM = min(ARM(ant) + (P − ETP), CAD);  NEG.AC = CAD·ln(ARM/CAD)
    ALT = ARM − ARM(ant)
    ETR = ETP se P − ETP ≥ 0, senão P − ALT
    DEF = ETP − ETR
    EXC = (P − ETP) − ALT quando ARM = CAD, senão 0
"""

from __future__ import annotations

import math
from calendar import monthrange

import numpy as np
import pandas as pd

MESES_NOME = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# ---------------------------------------------------------------------------
# Evapotranspiração potencial (Thornthwaite, 1948)
# ---------------------------------------------------------------------------


def fotoperiodo(lat_graus: float, dia_juliano) -> np.ndarray:
    """Duração do dia (h): δ = 23,45·sen[360/365·(DJ − 80)], N = 2·arccos(−tgφ·tgδ)/15
    (como em Pereira, Angelocci & Sentelhas, 2002)."""
    dj = np.asarray(dia_juliano, dtype=float)
    decl = np.radians(23.45 * np.sin(np.radians(360.0 / 365.0 * (dj - 80.0))))
    phi = np.radians(lat_graus)
    x = np.clip(-np.tan(phi) * np.tan(decl), -1.0, 1.0)
    hn = np.degrees(np.arccos(x))
    return 2.0 * hn / 15.0


def indice_calor(t_normais) -> tuple[float, float]:
    """Índice de calor anual I e expoente a a partir das 12 normais de temperatura."""
    t = np.asarray(t_normais, dtype=float)
    t = t[np.isfinite(t)]
    I = float(np.sum(np.power(0.2 * t[t > 0], 1.514)))
    if I <= 0:
        raise ValueError("Índice de calor nulo: verifique as temperaturas")
    a = 6.75e-7 * I ** 3 - 7.71e-5 * I ** 2 + 1.7912e-2 * I + 0.49239
    return I, a


def etp_padrao(t, I: float, a: float) -> np.ndarray:
    """ETP padrão (mm/mês de 30 dias com 12 h de fotoperíodo)."""
    t = np.asarray(t, dtype=float)
    saida = np.zeros_like(t)
    quente = t >= 26.5
    normal = (t > 0) & ~quente
    saida[normal] = 16.0 * np.power(10.0 * t[normal] / I, a)
    saida[quente] = -415.85 + 32.24 * t[quente] - 0.43 * t[quente] ** 2
    saida[~np.isfinite(t)] = np.nan
    return saida


def etp_mensal(t_mensal, anos, meses, lat: float, I: float, a: float) -> np.ndarray:
    """ETP de cada mês (fotoperíodo do dia 15, nº real de dias do mês)."""
    anos = np.asarray(anos, dtype=int)
    meses = np.asarray(meses, dtype=int)
    dj15 = np.array([pd.Timestamp(year=int(y), month=int(m), day=15).dayofyear for y, m in zip(anos, meses)])
    nd = np.array([monthrange(int(y), int(m))[1] for y, m in zip(anos, meses)], dtype=float)
    return etp_padrao(t_mensal, I, a) * (fotoperiodo(lat, dj15) / 12.0) * (nd / 30.0)


def etp_diaria(t_diaria, datas: pd.Series, lat: float, I: float, a: float) -> np.ndarray:
    dj = pd.to_datetime(datas).dt.dayofyear.to_numpy()
    return etp_padrao(t_diaria, I, a) * (fotoperiodo(lat, dj) / 12.0) / 30.0


# ---------------------------------------------------------------------------
# Balanço hídrico
# ---------------------------------------------------------------------------


def balanco_sequencial(p, etp, cad: float, arm_inicial: float) -> pd.DataFrame:
    """Thornthwaite & Mather passo a passo (mensal ou diário)."""
    if cad <= 0:
        raise ValueError("A CAD deve ser maior que zero")
    p = np.asarray(p, dtype=float)
    etp = np.asarray(etp, dtype=float)
    arm_ant = float(min(max(arm_inicial, 1e-9), cad))
    neg_ant = cad * math.log(arm_ant / cad)

    linhas = []
    for pi, ei in zip(p, etp):
        w = pi - ei
        if w < 0:
            neg = neg_ant + w
            arm = cad * math.exp(neg / cad)
        else:
            arm = min(arm_ant + w, cad)
            neg = cad * math.log(arm / cad) if arm < cad else 0.0
        alt = arm - arm_ant
        etr = ei if w >= 0 else pi - alt
        defi = ei - etr
        exc = (w - alt) if (w >= 0 and arm >= cad - 1e-9) else 0.0
        linhas.append((pi, ei, w, neg, arm, alt, etr, defi, exc))
        arm_ant, neg_ant = arm, neg

    return pd.DataFrame(linhas, columns=["p_mm", "etp_mm", "p_etp_mm", "neg_ac_mm", "arm_mm",
                                         "alt_mm", "etr_mm", "def_mm", "exc_mm"])


def balanco_normal(p12, etp12, cad: float, max_ciclos: int = 100) -> tuple[pd.DataFrame, float]:
    """Balanço normal (12 meses) em regime permanente: repete o ciclo anual até convergir.

    Retorna a tabela e o armazenamento ao fim de dezembro (usado como condição
    inicial do balanço sequencial).
    """
    arm = cad
    for _ in range(max_ciclos):
        tab = balanco_sequencial(p12, etp12, cad, arm)
        novo = float(tab["arm_mm"].iloc[-1])
        if abs(novo - arm) < 0.01:
            arm = novo
            break
        arm = novo
    tab = balanco_sequencial(p12, etp12, cad, arm)
    tab.insert(0, "mes", np.arange(1, 13))
    return tab, arm


# ---------------------------------------------------------------------------
# Classificação climática (Thornthwaite, 1948)
# ---------------------------------------------------------------------------

_TIPOS = [
    (100, "A", "Superúmido"),
    (80, "B4", "Úmido"),
    (60, "B3", "Úmido"),
    (40, "B2", "Úmido"),
    (20, "B1", "Úmido"),
    (0, "C2", "Subúmido"),
    (-33.3, "C1", "Subúmido seco"),
    (-66.7, "D", "Semiárido"),
]


def indices_climaticos(etp: float, defi: float, exc: float) -> dict:
    ih = float(100 * exc / etp) if etp else None
    ia = float(100 * defi / etp) if etp else None
    im = ih - 0.6 * ia if ih is not None else None
    tipo, desc = "E", "Árido"
    if im is not None:
        for limite, t, d in _TIPOS:
            if im >= limite:
                tipo, desc = t, d
                break
    return {
        "indice_umidade_ih": None if ih is None else round(ih, 1),
        "indice_aridez_ia": None if ia is None else round(ia, 1),
        "indice_hidrico_im": None if im is None else round(im, 1),
        "tipo_climatico": tipo,
        "descricao": desc,
    }


# ---------------------------------------------------------------------------
# Rotina completa a partir de dados diários
# ---------------------------------------------------------------------------


def _preparar_diario(diario: pd.DataFrame) -> pd.DataFrame:
    d = diario.copy()
    d["dia"] = pd.to_datetime(d["dia"]).dt.normalize()
    if "temp_c" not in d:
        d["temp_c"] = np.nan
    if "temp_max_c" in d and "temp_min_c" in d:
        d["temp_c"] = d["temp_c"].fillna((d["temp_max_c"] + d["temp_min_c"]) / 2)
    return d[["dia", "chuva_mm", "temp_c"]].drop_duplicates("dia").sort_values("dia")


def _mensal(d: pd.DataFrame) -> pd.DataFrame:
    """Totais/médias mensais com a contagem de dias válidos."""
    g = d.groupby(d["dia"].dt.to_period("M"))
    m = pd.DataFrame({
        "p_obs": g["chuva_mm"].sum(min_count=1),
        "dias_p": g["chuva_mm"].count(),
        "t_obs": g["temp_c"].mean(),
        "dias_t": g["temp_c"].count(),
    })
    m.index.name = "mes"
    return m


def normais(d: pd.DataFrame) -> pd.DataFrame:
    """Normais por mês do calendário (só meses com dados suficientes entram na média)."""
    m = _mensal(d)
    if m.empty:
        return pd.DataFrame({"mes": range(1, 13), "p_mm": np.nan, "t_c": np.nan, "anos_p": 0, "anos_t": 0})
    m["nd"] = [p.days_in_month for p in m.index]
    m["mes_cal"] = [p.month for p in m.index]
    ok_p = m[m["dias_p"] >= 0.9 * m["nd"]]
    ok_t = m[m["dias_t"] >= 0.5 * m["nd"]]
    # Totais de meses com poucas falhas são corrigidos proporcionalmente
    p = (ok_p["p_obs"] * ok_p["nd"] / ok_p["dias_p"]).groupby(ok_p["mes_cal"]).mean()
    t = ok_t["t_obs"].groupby(ok_t["mes_cal"]).mean()
    tab = pd.DataFrame({"mes": range(1, 13)})
    tab["p_mm"] = tab["mes"].map(p)
    tab["t_c"] = tab["mes"].map(t)
    tab["anos_p"] = tab["mes"].map(ok_p.groupby("mes_cal").size()).fillna(0).astype(int)
    tab["anos_t"] = tab["mes"].map(ok_t.groupby("mes_cal").size()).fillna(0).astype(int)
    return tab


def calcular_balanco(
    diario: pd.DataFrame,
    lat: float,
    inicio: pd.Period,
    fim: pd.Period,
    cad: float = 100.0,
    escala: str = "mensal",
    diario_base_normais: pd.DataFrame | None = None,
) -> dict:
    """Balanço sequencial no intervalo [inicio, fim] (meses) + balanço normal do período.

    `diario` precisa das colunas dia, chuva_mm e temp_c (ou temp_max_c/temp_min_c).
    Falhas de chuva são completadas com a média diária normal do mês; falhas de
    temperatura, com a normal do mês. Tudo que for estimado é sinalizado.
    """
    if escala not in ("mensal", "diario"):
        raise ValueError("escala deve ser 'mensal' ou 'diario'")
    if fim < inicio:
        inicio, fim = fim, inicio

    avisos: list[str] = []
    d_all = _preparar_diario(diario)
    ini_ts, fim_ts = inicio.start_time, fim.end_time.normalize()
    d = d_all[(d_all["dia"] >= ini_ts) & (d_all["dia"] <= fim_ts)]
    if d.empty or (d["chuva_mm"].notna().sum() == 0):
        raise ValueError("Não há dados de chuva no período escolhido")

    meses_periodo = pd.period_range(inicio, fim, freq="M")

    # Normais: do próprio período se ele cobre os 12 meses; senão, de toda a série
    base = d
    tab_norm = normais(base)

    def _lacunas(t: pd.DataFrame) -> int:
        return int(t["t_c"].isna().sum() + t["p_mm"].isna().sum())

    if len(meses_periodo) < 12 or _lacunas(tab_norm) > 0:
        alternativa = _preparar_diario(diario_base_normais) if diario_base_normais is not None else d_all
        tab_alt = normais(alternativa)
        if _lacunas(tab_alt) <= _lacunas(tab_norm):
            base, tab_norm = alternativa, tab_alt
            avisos.append("Normais calculadas com toda a série disponível (o período escolhido é curto ou incompleto).")
    if tab_norm["t_c"].isna().any():
        faltam = [MESES_NOME[m - 1] for m in tab_norm.loc[tab_norm["t_c"].isna(), "mes"]]
        raise ValueError("Sem temperatura suficiente para calcular a ETP (meses sem dados: " + ", ".join(faltam) + ")")
    if tab_norm["p_mm"].isna().any():
        faltam = [MESES_NOME[m - 1] for m in tab_norm.loc[tab_norm["p_mm"].isna(), "mes"]]
        avisos.append("Sem chuva normal para: " + ", ".join(faltam) + " (considerado 0 mm no preenchimento).")
        tab_norm["p_mm"] = tab_norm["p_mm"].fillna(0.0)

    I, a = indice_calor(tab_norm["t_c"].to_numpy())
    p_norm = dict(zip(tab_norm["mes"], tab_norm["p_mm"]))
    t_norm = dict(zip(tab_norm["mes"], tab_norm["t_c"]))

    # Balanço normal (regime permanente) — também dá o ARM inicial
    nd_norm = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    dj15 = np.array([15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349])
    etp12 = etp_padrao(tab_norm["t_c"].to_numpy(), I, a) * (fotoperiodo(lat, dj15) / 12) * (nd_norm / 30)
    bh_norm, _ = balanco_normal(tab_norm["p_mm"].to_numpy(), etp12, cad)
    bh_norm.insert(1, "t_c", tab_norm["t_c"].to_numpy())
    mes_anterior = (inicio - 1).month
    arm_inicial = float(bh_norm.loc[bh_norm["mes"] == mes_anterior, "arm_mm"].iloc[0])

    # Série diária completa do período (com preenchimento das falhas)
    dias = pd.DataFrame({"dia": pd.date_range(ini_ts, fim_ts, freq="D")})
    dias = dias.merge(d, on="dia", how="left")
    mes_cal = dias["dia"].dt.month
    nd_mes = dias["dia"].dt.days_in_month
    dias["p_estimada"] = dias["chuva_mm"].isna()
    dias["t_estimada"] = dias["temp_c"].isna()
    dias["p_mm"] = dias["chuva_mm"].fillna(mes_cal.map(p_norm) / nd_mes)
    dias["t_c"] = dias["temp_c"].fillna(mes_cal.map(t_norm))

    # Agregação mensal
    per = dias["dia"].dt.to_period("M")
    gm = dias.groupby(per)
    mensal = pd.DataFrame({
        "p_mm": gm["p_mm"].sum(),
        "t_c": gm["t_c"].mean(),
        "dias_p_falha": gm["p_estimada"].sum(),
        "dias_t_falha": gm["t_estimada"].sum(),
        "nd": gm.size(),
    })
    mensal = mensal.reindex(meses_periodo)
    mensal["cobertura_p_pct"] = 100 * (1 - mensal["dias_p_falha"] / mensal["nd"])
    mensal["cobertura_t_pct"] = 100 * (1 - mensal["dias_t_falha"] / mensal["nd"])

    if escala == "mensal":
        etp = etp_mensal(mensal["t_c"].to_numpy(), [p.year for p in mensal.index], [p.month for p in mensal.index], lat, I, a)
        bh = balanco_sequencial(mensal["p_mm"].to_numpy(), etp, cad, arm_inicial)
        bh.insert(0, "t_c", mensal["t_c"].to_numpy())
        bh.insert(0, "fim", [p.end_time.normalize() for p in mensal.index])
        bh.insert(0, "inicio", [p.start_time for p in mensal.index])
        bh.insert(0, "periodo", [f"{MESES_NOME[p.month - 1]}/{p.year}" for p in mensal.index])
        bh["cobertura_p_pct"] = mensal["cobertura_p_pct"].to_numpy()
        bh["cobertura_t_pct"] = mensal["cobertura_t_pct"].to_numpy()
        seq = bh
        seq_mensal = bh
    else:
        etp = etp_diaria(dias["t_c"].to_numpy(), dias["dia"], lat, I, a)
        bh = balanco_sequencial(dias["p_mm"].to_numpy(), etp, cad, arm_inicial)
        bh.insert(0, "t_c", dias["t_c"].to_numpy())
        bh.insert(0, "fim", dias["dia"].to_numpy())
        bh.insert(0, "inicio", dias["dia"].to_numpy())
        bh.insert(0, "periodo", dias["dia"].dt.strftime("%d/%m/%Y").to_numpy())
        bh["p_estimada"] = dias["p_estimada"].to_numpy()
        bh["t_estimada"] = dias["t_estimada"].to_numpy()
        seq = bh
        # Resumo mensal do balanço diário
        bh_m = bh.assign(_per=per.to_numpy())
        g = bh_m.groupby("_per")
        seq_mensal = pd.DataFrame({
            "p_mm": g["p_mm"].sum(), "t_c": g["t_c"].mean(), "etp_mm": g["etp_mm"].sum(),
            "etr_mm": g["etr_mm"].sum(), "def_mm": g["def_mm"].sum(), "exc_mm": g["exc_mm"].sum(),
            "arm_mm": g["arm_mm"].last(),
        })
        seq_mensal["p_etp_mm"] = seq_mensal["p_mm"] - seq_mensal["etp_mm"]
        seq_mensal.insert(0, "periodo", [f"{MESES_NOME[p.month - 1]}/{p.year}" for p in seq_mensal.index])
        seq_mensal.insert(1, "inicio", [p.start_time for p in seq_mensal.index])
        seq_mensal["cobertura_p_pct"] = mensal["cobertura_p_pct"].reindex(seq_mensal.index).to_numpy()
        seq_mensal["cobertura_t_pct"] = mensal["cobertura_t_pct"].reindex(seq_mensal.index).to_numpy()
        seq_mensal = seq_mensal.reset_index(drop=True)

    falhas_p = int(dias["p_estimada"].sum())
    falhas_t = int(dias["t_estimada"].sum())
    if falhas_p:
        avisos.append(f"{falhas_p} dia(s) sem chuva registrada foram completados com a média diária normal do mês.")
    if falhas_t:
        avisos.append(f"{falhas_t} dia(s) sem temperatura foram completados com a normal do mês.")
    dados_reais = d["dia"]
    if dados_reais.min() > ini_ts + pd.Timedelta(days=31) or dados_reais.max() < fim_ts - pd.Timedelta(days=31):
        avisos.append(
            f"Os dados observados vão de {dados_reais.min():%d/%m/%Y} a {dados_reais.max():%d/%m/%Y}; "
            "fora disso os valores são estimados pelas normais."
        )

    tot = {k: round(float(seq[k].sum()), 1) for k in ("p_mm", "etp_mm", "etr_mm", "def_mm", "exc_mm")}
    tot["alt_mm"] = round(float(seq["alt_mm"].sum()), 1)
    tot_norm = {k: round(float(bh_norm[k].sum()), 1) for k in ("p_mm", "etp_mm", "etr_mm", "def_mm", "exc_mm")}

    base_dias = base["dia"]
    return {
        "parametros": {
            "metodo": "Thornthwaite (1948) + Thornthwaite & Mather (1955)",
            "cad_mm": cad,
            "lat": lat,
            "inicio": inicio.start_time.date().isoformat(),
            "fim": fim.end_time.date().isoformat(),
            "meses": len(meses_periodo),
            "escala": escala,
            "arm_inicial_mm": round(arm_inicial, 1),
        },
        "indice_calor": {"I": round(I, 2), "a": round(a, 3)},
        "base_normais": {
            "inicio": base_dias.min().date().isoformat(),
            "fim": base_dias.max().date().isoformat(),
        },
        "normais": tab_norm.round(2).to_dict(orient="records"),
        "normal": bh_norm.round(2).to_dict(orient="records"),
        "totais_normal": tot_norm,
        "indices": indices_climaticos(tot_norm["etp_mm"], tot_norm["def_mm"], tot_norm["exc_mm"]),
        "sequencial": seq,
        "sequencial_mensal": seq_mensal,
        "totais": tot,
        "avisos": avisos,
    }
