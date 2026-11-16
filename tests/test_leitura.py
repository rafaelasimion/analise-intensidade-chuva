import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from hidro.esalq import ler_arquivo_esalq
from hidro.inmet import diario_inmet, ler_csv_inmet, processar_zip


def _toa5(colunas, unidades, linhas) -> list[list]:
    cab = [["TOA5", "ESALQ", "CR1000", "1234", "CR1000.Std", "CPU:prog.CR1", "123", "Tabela15"]]
    return cab + [colunas, unidades, ["", "", *(["Avg"] * (len(colunas) - 2))]] + linhas


def _arquivo_esalq(formato="xlsx"):
    colunas = ["TIMESTAMP", "RECORD", "Temp_Ar_Avg", "Temp_Ar_Max", "UR_Avg", "Vel_Vento_Avg",
               "Dir_Vento", "Rajada_Max", "Rad_Global_Avg", "Pressao_Avg", "Chuva_mm_Tot", "BattV_Min", "PTemp_C"]
    unidades = ["TS", "RN", "Deg C", "Deg C", "%", "km/h", "graus", "km/h", "kW/m^2", "kPa", "mm", "Volts", "Deg C"]
    t = pd.date_range("2026-01-01 00:15", periods=8, freq="15min")
    linhas = []
    for i, ts in enumerate(t):
        linhas.append([ts.strftime("%Y-%m-%d %H:%M:%S"), i, 22 + i * 0.1, 22.5 + i * 0.1, 80, 7.2, 180,
                       36, 0.5, 95.0, [0, 0.254, 7999, 0.508, 200, 0, 0, 0][i], 12.5, 25])
    tab = _toa5(colunas, unidades, linhas)
    if formato == "xlsx":
        buf = io.BytesIO()
        pd.DataFrame(tab).to_excel(buf, header=False, index=False)
        return buf.getvalue()
    return "\n".join(",".join(f'"{v}"' for v in linha) for linha in tab).encode()


@pytest.mark.parametrize("formato", ["xlsx", "csv"])
def test_le_toa5_e_identifica_variaveis(formato):
    df, info = ler_arquivo_esalq(_arquivo_esalq(formato))
    m = info["mapeamento"]
    assert m["chuva_mm"] == "Chuva_mm_Tot"
    assert m["temp_c"] == "Temp_Ar_Avg" and m["temp_max_c"] == "Temp_Ar_Max"
    assert m["ur_pct"] == "UR_Avg"
    assert m["vento_ms"] == "Vel_Vento_Avg" and m["vento_max_ms"] == "Rajada_Max"
    assert m["vento_dir_graus"] == "Dir_Vento"
    assert m["rad_w_m2"] == "Rad_Global_Avg" and m["pressao_hpa"] == "Pressao_Avg"
    assert "BattV_Min" not in m.values() and "PTemp_C" not in m.values()
    assert len(df) == 8
    # Conversões de unidade
    assert df["vento_ms"].iloc[0] == pytest.approx(2.0)      # 7,2 km/h
    assert df["vento_max_ms"].iloc[0] == pytest.approx(10.0)  # 36 km/h
    assert df["rad_w_m2"].iloc[0] == pytest.approx(500)       # 0,5 kW/m²
    assert df["pressao_hpa"].iloc[0] == pytest.approx(950)    # 95 kPa
    # Limpeza da chuva (7999 = erro do sensor, 200 mm em 15 min = descartado)
    chuva = df["chuva_mm"].tolist()
    assert chuva[1] == pytest.approx(0.254) and np.isnan(chuva[2]) and np.isnan(chuva[4])


def _csv_inmet(codigo="A726", datas=("2024-01-01", "2024-01-02"), novo=True) -> bytes:
    meta = [
        "REGIAO:;SE", "UF:;SP", "ESTACAO:;PIRACICABA", f"CODIGO (WMO):;{codigo}",
        "LATITUDE:;-22,70305555", "LONGITUDE:;-47,62333332", "ALTITUDE:;566,46", "DATA DE FUNDACAO:;26/09/06",
    ]
    cab = ("Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);PRESSAO ATMOSFERICA AO NIVEL DA ESTACAO, HORARIA (mB);"
           "PRESSÃO ATMOSFERICA MAX.NA HORA ANT. (AUT) (mB);PRESSÃO ATMOSFERICA MIN. NA HORA ANT. (AUT) (mB);"
           "RADIACAO GLOBAL (Kj/m²);TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);TEMPERATURA DO PONTO DE ORVALHO (°C);"
           "TEMPERATURA MÁXIMA NA HORA ANT. (AUT) (°C);TEMPERATURA MÍNIMA NA HORA ANT. (AUT) (°C);"
           "TEMPERATURA ORVALHO MAX. NA HORA ANT. (AUT) (°C);TEMPERATURA ORVALHO MIN. NA HORA ANT. (AUT) (°C);"
           "UMIDADE REL. MAX. NA HORA ANT. (AUT) (%);UMIDADE REL. MIN. NA HORA ANT. (AUT) (%);"
           "UMIDADE RELATIVA DO AR, HORARIA (%);VENTO, DIREÇÃO HORARIA (gr) (° (gr));VENTO, RAJADA MAXIMA (m/s);"
           "VENTO, VELOCIDADE HORARIA (m/s);")
    linhas = []
    for d in datas:
        for h in range(24):
            data = d.replace("-", "/") if novo else d
            hora = f"{h:02d}00 UTC" if novo else f"{h:02d}:00"
            chuva = "1,2" if h == 15 else ("-9999" if h == 16 else "0")
            temp = f"{20 + h % 10},5"
            linhas.append(f"{data};{hora};{chuva};940,1;940,5;939,8;{1000 if 9 < h < 21 else -9999};{temp};15;"
                          f"{21 + h % 10};{19 + h % 10};16;14;90;80;85;120;5,5;2,1;")
    return ("\n".join(meta + [cab] + linhas)).encode("latin-1")


@pytest.mark.parametrize("novo", [True, False])
def test_le_csv_inmet(novo):
    meta, h = ler_csv_inmet(_csv_inmet(novo=novo))
    assert meta["codigo"] == "A726" and meta["fundacao"] == "2006-09-26"
    assert meta["lat"] == pytest.approx(-22.70305555)
    assert len(h) == 48
    # Hora UTC convertida para hora local (−3 h)
    assert h["data_hora"].iloc[0] == pd.Timestamp("2023-12-31 21:00")
    assert h["chuva_mm"].max() == pytest.approx(1.2) and h["chuva_mm"].isna().sum() == 2
    d = diario_inmet(h)
    linha = d[d["dia"] == pd.Timestamp("2024-01-01")].iloc[0]
    assert linha["chuva_mm"] == pytest.approx(1.2)
    assert linha["rad_mj_m2"] == pytest.approx(11.0)  # 11 h com 1000 kJ/m²
    assert linha["vento_ms"] == pytest.approx(2.1)


def test_processar_zip(tmp_path):
    z = tmp_path / "2024.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("INMET_SE_SP_A726_PIRACICABA_01-01-2024_A_31-12-2024.CSV", _csv_inmet())
        f.writestr("INMET_SE_MG_A999_OUTRA_01-01-2024_A_31-12-2024.CSV", _csv_inmet("A999"))
    diario, metas = processar_zip(z, "SP")
    assert set(diario["codigo"]) == {"A726"}
    assert [m["codigo"] for m in metas] == ["A726"]


# Colunas reais do diario2026.xls da ESALQ (nov/2026)
COLUNAS_ESALQ_2026 = [
    ("TIMESTAMP", "TS"), ("RECORD", "RN"), ("BattV_Avg", "Volts"), ("Tar_AVG", "Deg C"), ("UR_inst", "%"),
    ("Vvento_ms_AVG", "meters/second"), ("Dvento_G", "Deg"), ("Qg_AVG", "W/m^2"), ("PAR_AVG", "umol/s/m^2"),
    ("Rn_Avg", "W/m^2"), ("Chuva_mm", "mm"), ("Patm_kPa_AVG", "kPa"), ("rQg_AVG", "W/m^2"), ("Qatm_AVG", "W/m^2"),
    ("Qsup_AVG", "W/m^2"), ("Boc_AVG", "W/m^2"), ("Bol_AVG", "W/m^2"), ("Albedo_Avg", "W/m^2"),
    ("QatmC_AVG", "W/m^2"), ("QsupC_AVG", "W/m^2"), ("Vvento_ms_S_WVT", "meters/second"),
    ("Dvento_D1_WVT", "Deg"), ("Dvento_SD1_WVT", "Deg"), ("PainelT", "Deg C"),
]


def test_colunas_reais_da_esalq():
    nomes = [c for c, _ in COLUNAS_ESALQ_2026]
    unidades = [u for _, u in COLUNAS_ESALQ_2026]
    t = pd.date_range("2026-01-01 00:15", periods=4, freq="15min")
    linhas = []
    for i, ts in enumerate(t):
        valores = {
            "TIMESTAMP": ts.strftime("%Y-%m-%d %H:%M:%S"), "RECORD": i, "BattV_Avg": 13.1, "Tar_AVG": 21.5 + i,
            "UR_inst": 88, "Vvento_ms_AVG": 2.4, "Dvento_G": 140, "Qg_AVG": 0, "PAR_AVG": 0, "Rn_Avg": -40,
            "Chuva_mm": 0.254 * i, "Patm_kPa_AVG": 94.8, "rQg_AVG": 0, "Qatm_AVG": 380, "Qsup_AVG": 420,
            "Boc_AVG": 0, "Bol_AVG": -40, "Albedo_Avg": 0, "QatmC_AVG": 380, "QsupC_AVG": 420,
            "Vvento_ms_S_WVT": 2.5, "Dvento_D1_WVT": 135, "Dvento_SD1_WVT": 20, "PainelT": 25,
        }
        linhas.append([valores[n] for n in nomes])
    buf = io.BytesIO()
    pd.DataFrame(_toa5(nomes, unidades, linhas)).to_excel(buf, header=False, index=False)

    df, info = ler_arquivo_esalq(buf.getvalue())
    assert info["mapeamento"] == {
        "chuva_mm": "Chuva_mm",
        "temp_c": "Tar_AVG",
        "ur_pct": "UR_inst",
        "vento_ms": "Vvento_ms_AVG",
        "vento_dir_graus": "Dvento_D1_WVT",
        "rad_w_m2": "Qg_AVG",
        "pressao_hpa": "Patm_kPa_AVG",
    }
    assert df["vento_ms"].tolist() == pytest.approx([2.4] * 4)
    assert df["vento_dir_graus"].iloc[0] == pytest.approx(135)
    assert df["pressao_hpa"].iloc[0] == pytest.approx(948)
    assert df["vento_max_ms"].isna().all()  # a ESALQ não registra rajada na tabela de 15 min
