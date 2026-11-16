"""Testa o script de atualização e o download ao vivo sem acessar a internet."""

import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from tests.test_leitura import _arquivo_esalq, _csv_inmet

RAIZ = Path(__file__).resolve().parent.parent


def _modulo_script():
    spec = importlib.util.spec_from_file_location("atualizar_dados", RAIZ / "scripts" / "atualizar_dados.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def script(tmp_path, monkeypatch):
    mod = _modulo_script()
    monkeypatch.setattr(mod, "DIR_ESALQ", tmp_path / "esalq")
    monkeypatch.setattr(mod, "DIR_INMET_DIARIO", tmp_path / "inmet" / "diario")
    monkeypatch.setattr(mod, "ARQ_ATUALIZACAO", tmp_path / "atualizacao.json")
    monkeypatch.setattr(mod.inmet, "ARQ_ESTACOES", tmp_path / "inmet" / "estacoes_sp.json")
    return mod


def test_atualizar_esalq(script, monkeypatch, tmp_path):
    def falso_baixar(url, **_):
        return _arquivo_esalq("xlsx") if "2026" in url else None  # só 2026 "existe"

    monkeypatch.setattr(script, "baixar", falso_baixar)
    script.atualizar_esalq([2025, 2026], desde=2025, forcar=False)

    arq = tmp_path / "esalq" / "esalq_2026.csv.gz"
    df = pd.read_csv(arq, parse_dates=["data_hora"])
    assert len(df) == 8 and df["vento_ms"].notna().all()
    anos = json.loads((tmp_path / "esalq" / "anos.json").read_text("utf-8"))
    assert anos["disponiveis"] == [2026] and 2025 in anos["inexistentes"]
    colunas = json.loads((tmp_path / "esalq" / "colunas.json").read_text("utf-8"))
    assert colunas["2026"]["mapeamento"]["vento_ms"] == "Vel_Vento_Avg"


def test_atualizar_inmet(script, monkeypatch, tmp_path):
    def falso_baixar(url, destino=None, **_):
        with zipfile.ZipFile(destino, "w") as z:
            z.writestr("2024/INMET_SE_SP_A726_PIRACICABA_01-01-2024_A_31-12-2024.CSV", _csv_inmet())
        return b""

    monkeypatch.setattr(script, "baixar", falso_baixar)
    script.atualizar_inmet([2024], forcar=True)

    diario = pd.read_csv(tmp_path / "inmet" / "diario" / "inmet_sp_2024.csv.gz")
    assert set(diario["codigo"]) == {"A726"}
    catalogo = json.loads((tmp_path / "inmet" / "estacoes_sp.json").read_text("utf-8"))["estacoes"]
    a726 = next(e for e in catalogo if e["codigo"] == "A726")
    # 31/12 (hora local) só tem 3 horas de dados e é descartado (mínimo de 18 h)
    assert a726["inicio_dados"] == "2024-01-01" and a726["fim_dados"] == "2024-01-02"


def test_download_ao_vivo_junta_com_repositorio(monkeypatch):
    from hidro import armazenamento
    from hidro.esalq import ler_arquivo_esalq

    ano = armazenamento.hoje().year
    novo, info = ler_arquivo_esalq(_arquivo_esalq("xlsx"))
    novo["data_hora"] = novo["data_hora"].apply(lambda t: t.replace(year=ano))
    monkeypatch.setattr(armazenamento, "baixar_ano", lambda a, **_: (novo, info))
    armazenamento._cache_vivo.clear()
    try:
        df, meta = armazenamento.carregar_ano(ano, atualizar=True)
        assert meta["origem"] == "ao_vivo"
        assert df["data_hora"].dt.year.eq(ano).all()
        assert df["vento_ms"].notna().sum() >= 8
    finally:
        armazenamento._cache_vivo.clear()


def test_nasa_power(monkeypatch):
    from hidro import nasa_power
    from hidro.balanco import calcular_balanco

    dias = pd.date_range("2015-01-01", "2024-12-31")
    chaves = dias.strftime("%Y%m%d")
    t = [24 - 6 * abs((d.month - 7) / 6) + 0 for d in dias]
    resposta = {"properties": {"parameter": {
        "PRECTOTCORR": dict(zip(chaves, [4.0 if d.month in (1, 2, 3, 10, 11, 12) else 0.8 for d in dias])),
        "T2M": dict(zip(chaves, t)),
        "T2M_MAX": dict(zip(chaves, [x + 5 for x in t])),
        "T2M_MIN": dict(zip(chaves, [-999.0] + [x - 5 for x in t[1:]])),
    }}}

    class Falsa:
        def raise_for_status(self):
            pass

        def json(self):
            return resposta

    monkeypatch.setattr(nasa_power.requests, "get", lambda *a, **k: Falsa())
    nasa_power._baixar.cache_clear()
    d = nasa_power.carregar_diario(-22.7, -47.6, dias[0].date(), dias[-1].date())
    assert d["temp_min_c"].isna().sum() == 1  # -999 vira falha
    r = calcular_balanco(d, -22.7, pd.Period("2020-01", "M"), pd.Period("2024-12", "M"))
    assert len(r["sequencial"]) == 60
    nasa_power._baixar.cache_clear()
