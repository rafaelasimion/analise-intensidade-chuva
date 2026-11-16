import math

import numpy as np
import pandas as pd
import pytest

from hidro.balanco import (
    balanco_normal, balanco_sequencial, calcular_balanco, etp_padrao, fotoperiodo, indice_calor,
    indices_climaticos,
)

# Normais aproximadas de Piracicaba (só para teste)
T_PIRA = [24.1, 24.4, 23.8, 21.9, 19.2, 17.8, 17.4, 19.4, 20.9, 22.3, 23.1, 23.6]
P_PIRA = [230, 185, 150, 65, 55, 45, 30, 30, 60, 120, 140, 205]


def test_indice_calor_e_expoente():
    I, a = indice_calor(T_PIRA)
    esperado = sum((0.2 * t) ** 1.514 for t in T_PIRA)
    assert I == pytest.approx(esperado)
    assert a == pytest.approx(6.75e-7 * I ** 3 - 7.71e-5 * I ** 2 + 1.7912e-2 * I + 0.49239)
    assert 95 < I < 110  # ordem de grandeza típica para o interior de SP


def test_etp_padrao_faixas():
    I, a = indice_calor(T_PIRA)
    e = etp_padrao([0, 10, 26.4, 26.5, 30], I, a)
    assert e[0] == 0
    assert e[1] == pytest.approx(16 * (100 / I) ** a)
    assert e[3] == pytest.approx(-415.85 + 32.24 * 26.5 - 0.43 * 26.5 ** 2)
    # As duas fórmulas se encontram perto de 26,5 °C
    assert abs(e[2] - e[3]) < 5


def test_fotoperiodo():
    # Equador: ~12 h o ano todo; hemisfério sul: dias mais longos em dezembro
    assert fotoperiodo(0, [1, 172, 355]) == pytest.approx([12, 12, 12], abs=0.05)
    n_jun, n_dez = fotoperiodo(-22.7, [172, 355])
    assert n_dez > 13 > 11 > n_jun


def test_sequencial_conserva_massa_e_limites():
    rng = np.random.default_rng(1)
    p = rng.gamma(0.8, 120, size=60)
    etp = rng.uniform(40, 140, size=60)
    cad = 100
    tab = balanco_sequencial(p, etp, cad, arm_inicial=60)
    assert (tab["arm_mm"] <= cad + 1e-9).all() and (tab["arm_mm"] > 0).all()
    assert (tab["etr_mm"] <= tab["etp_mm"] + 1e-9).all()
    assert (tab["def_mm"] >= -1e-9).all() and (tab["exc_mm"] >= -1e-9).all()
    # P = ETR + EXC + ΔARM
    delta = tab["arm_mm"].iloc[-1] - 60
    assert p.sum() == pytest.approx(tab["etr_mm"].sum() + tab["exc_mm"].sum() + delta)
    # ETP = ETR + DEF
    assert etp.sum() == pytest.approx(tab["etr_mm"].sum() + tab["def_mm"].sum())


def test_sequencial_casos_extremos():
    # Sem chuva: o armazenamento cai exponencialmente
    tab = balanco_sequencial([0, 0, 0], [50, 50, 50], 100, 100)
    assert tab["arm_mm"].tolist() == pytest.approx([100 * math.exp(-0.5), 100 * math.exp(-1), 100 * math.exp(-1.5)])
    assert tab["etr_mm"].iloc[0] == pytest.approx(100 - 100 * math.exp(-0.5))
    # Muita chuva com solo cheio: tudo vira excedente
    tab = balanco_sequencial([300], [100], 100, 100)
    assert tab["exc_mm"].iloc[0] == pytest.approx(200)
    assert tab["def_mm"].iloc[0] == pytest.approx(0)


def test_normal_converge_e_fecha_o_ano():
    I, a = indice_calor(T_PIRA)
    etp = etp_padrao(T_PIRA, I, a)
    tab, arm_dez = balanco_normal(P_PIRA, etp, 100)
    # Regime permanente: ARM de dezembro = ARM inicial
    assert tab["arm_mm"].iloc[-1] == pytest.approx(arm_dez, abs=0.02)
    assert tab["alt_mm"].sum() == pytest.approx(0, abs=0.05)
    assert sum(P_PIRA) == pytest.approx(tab["etr_mm"].sum() + tab["exc_mm"].sum(), abs=0.1)
    # Inverno seco em Piracicaba: déficit em jul/ago, excedente no verão
    assert tab.loc[tab["mes"] == 8, "def_mm"].iloc[0] > 0
    assert tab.loc[tab["mes"] == 1, "exc_mm"].iloc[0] > 0


def test_classificacao():
    assert indices_climaticos(1000, 0, 1200)["tipo_climatico"] == "A"
    assert indices_climaticos(1000, 0, 300)["tipo_climatico"] == "B1"
    assert indices_climaticos(1000, 500, 0)["tipo_climatico"] == "C1"
    assert indices_climaticos(1000, 900, 0)["tipo_climatico"] == "D"


def _diario_sintetico(anos=(2015, 2024), falhas=False):
    dias = pd.date_range(f"{anos[0]}-01-01", f"{anos[1]}-12-31", freq="D")
    rng = np.random.default_rng(7)
    m = dias.month - 1
    t = np.array(T_PIRA)[m] + rng.normal(0, 1.5, len(dias))
    p_dia = np.array(P_PIRA)[m] / dias.days_in_month
    chuva = np.where(rng.random(len(dias)) < 0.3, p_dia / 0.3 * rng.gamma(1, 1, len(dias)), 0.0)
    df = pd.DataFrame({"dia": dias, "chuva_mm": chuva, "temp_c": t})
    if falhas:
        df.loc[df.sample(frac=0.05, random_state=3).index, ["chuva_mm", "temp_c"]] = np.nan
    return df


def test_calcular_balanco_mensal_e_diario():
    d = _diario_sintetico(falhas=True)
    r = calcular_balanco(d, -22.7, pd.Period("2020-01", "M"), pd.Period("2024-12", "M"), 100, "mensal")
    seq = r["sequencial"]
    assert len(seq) == 60
    assert r["parametros"]["meses"] == 60
    assert r["indices"]["tipo_climatico"] in {"B1", "B2", "B3", "B4", "C2", "A"}
    assert any("completados" in a for a in r["avisos"])
    tot = r["totais"]
    assert tot["p_mm"] == pytest.approx(tot["etr_mm"] + tot["exc_mm"] + tot["alt_mm"], abs=0.5)

    rd = calcular_balanco(d, -22.7, pd.Period("2024-01", "M"), pd.Period("2024-03", "M"), 100, "diario")
    assert len(rd["sequencial"]) == 31 + 29 + 31
    assert len(rd["sequencial_mensal"]) == 3
    # Período curto: normais vêm da série toda
    assert rd["base_normais"]["inicio"].startswith("2015")


def test_calcular_balanco_sem_temperatura():
    d = _diario_sintetico()
    d["temp_c"] = np.nan
    with pytest.raises(ValueError, match="temperatura"):
        calcular_balanco(d, -22.7, pd.Period("2020-01", "M"), pd.Period("2020-12", "M"))
