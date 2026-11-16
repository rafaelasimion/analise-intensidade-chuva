import numpy as np
import pandas as pd
import pytest

from hidro.esalq import adicionar_derivados
from hidro.eventos import eventos_chuva, intensidade_simples, maximas_anuais


def _serie(chuvas: dict[str, float], inicio="2025-01-01 00:15", fim="2025-01-03 00:00"):
    t = pd.date_range(inicio, fim, freq="15min")
    df = pd.DataFrame({"data_hora": t, "chuva_mm": 0.0})
    for quando, mm in chuvas.items():
        df.loc[df["data_hora"] == pd.Timestamp(quando), "chuva_mm"] = mm
    for c in ["temp_c", "temp_max_c", "temp_min_c", "ur_pct", "vento_ms", "vento_max_ms",
              "vento_dir_graus", "rad_w_m2", "pressao_hpa"]:
        df[c] = np.nan
    return adicionar_derivados(df)


def test_separa_eventos_pelo_periodo_seco():
    df = _serie({
        "2025-01-01 10:15": 2.0, "2025-01-01 10:30": 6.0, "2025-01-01 10:45": 1.0,  # evento A
        "2025-01-01 13:00": 0.5,                                                   # 2h depois -> ainda A
        "2025-01-01 22:00": 4.0,                                                   # 9h depois -> B
    })
    ev = eventos_chuva(df, intervalo_seco_h=6, chuva_min_mm=0)
    assert len(ev) == 2
    a, b = ev.iloc[0], ev.iloc[1]
    assert a["chuva_mm"] == pytest.approx(9.5)
    assert a["inicio"] == pd.Timestamp("2025-01-01 10:00")
    assert a["fim"] == pd.Timestamp("2025-01-01 13:00")
    assert a["duracao_min"] == 180
    assert a["intensidade_media_mm_h"] == pytest.approx(9.5 / 3, abs=1e-3)
    assert a["i15_mm_h"] == pytest.approx(24.0)
    assert a["i30_mm_h"] == pytest.approx((6 + 2) * 2)
    assert a["i60_mm_h"] == pytest.approx(9.0)
    # Evento de um único intervalo
    assert b["duracao_min"] == 15 and b["i15_mm_h"] == pytest.approx(16.0) and b["i30_mm_h"] == pytest.approx(8.0)

    # Com 1 h de período seco, A se divide em dois
    assert len(eventos_chuva(df, intervalo_seco_h=1, chuva_min_mm=0)) == 3
    # Filtro de chuva mínima
    assert len(eventos_chuva(df, intervalo_seco_h=6, chuva_min_mm=5)) == 1


def test_intensidade_simples():
    assert intensidade_simples(10, 30) == pytest.approx(20)
    with pytest.raises(ValueError):
        intensidade_simples(10, 0)


def test_maximas_anuais():
    df = _serie({"2025-01-01 10:15": 2.0, "2025-01-01 10:30": 6.0, "2025-01-01 10:45": 1.0})
    mx = maximas_anuais(df, [15, 30, 60])
    v = {x["duracao_min"]: x for x in mx["anos"][0]["valores"]}
    assert v[15]["chuva_mm"] == pytest.approx(6.0) and v[15]["intensidade_mm_h"] == pytest.approx(24.0)
    assert v[30]["chuva_mm"] == pytest.approx(8.0)
    assert v[60]["chuva_mm"] == pytest.approx(9.0) and v[60]["intensidade_mm_h"] == pytest.approx(9.0)
    assert mx["anos"][0]["chuva_max_dia_mm"] == pytest.approx(9.0)


def test_registro_da_meia_noite_pertence_ao_dia_anterior():
    df = _serie({"2025-01-02 00:00": 3.0})
    assert df.loc[df["data_hora"] == pd.Timestamp("2025-01-02 00:00"), "dia"].iloc[0] == pd.Timestamp("2025-01-01")
