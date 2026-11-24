"""Testa o script de atualização e o download ao vivo sem acessar a internet."""

import importlib.util
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
    monkeypatch.setattr(mod, "DIR_INMET_HORARIO", tmp_path / "inmet" / "horario")
    monkeypatch.setattr(mod, "ARQ_PACOTES_INMET", tmp_path / "inmet" / "pacotes.json")
    monkeypatch.setattr(mod, "ARQ_ATUALIZACAO", tmp_path / "atualizacao.json")
    monkeypatch.setattr(mod, "_versao_remota", lambda url: {"tamanho": "123", "modificado": "ontem"})
    monkeypatch.setattr(mod.inmet, "ARQ_ESTACOES", tmp_path / "inmet" / "estacoes_sp.json")
    monkeypatch.setattr(mod.inmet, "DIR_INMET_DIARIO", tmp_path / "inmet" / "diario")
    monkeypatch.setattr(mod.inmet, "DIR_INMET_HORARIO", tmp_path / "inmet" / "horario")
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
    baixados = []

    def falso_baixar(url, destino=None, **_):
        baixados.append(url)
        ano = url.rsplit("/", 1)[1][:4]
        datas = ("2024-01-01", "2024-01-02", "2024-12-31") if ano == "2024" else ("2025-01-01",)
        with zipfile.ZipFile(destino, "w") as z:
            z.writestr(f"{ano}/INMET_SE_SP_A726_PIRACICABA_01-01-{ano}_A_31-12-{ano}.CSV", _csv_inmet(datas=datas))
            # Estação "de SP" fora do estado (a C891 fica na Antártida): ignorada
            z.writestr(f"{ano}/INMET_SE_SP_C891_CRIOSFERA_01-01-{ano}_A_31-12-{ano}.CSV",
                       _csv_inmet("C891", datas=datas).replace(b"-22,70305555", b"-84,0"))
        return b""

    monkeypatch.setattr(script, "baixar", falso_baixar)
    script.atualizar_inmet([2024], forcar=True)

    # Horário por estação e ano (o ano é o do dia: 00:00 de 1º/jan fica no ano anterior)
    pasta = tmp_path / "inmet" / "horario"
    assert sorted(p.name for p in pasta.iterdir()) == ["A726"]
    assert sorted(p.name for p in (pasta / "A726").iterdir()) == ["2023.csv.gz", "2024.csv.gz"]
    h = pd.read_csv(pasta / "A726" / "2024.csv.gz", parse_dates=["data_hora"])
    assert h["data_hora"].min() == pd.Timestamp("2024-01-01 01:00")
    assert h["rad_w_m2"].max() == pytest.approx(1000 / 3.6, abs=1)
    assert h["vento_dir_graus"].iloc[0] == 120

    diario = pd.read_csv(tmp_path / "inmet" / "diario" / "inmet_sp_2024.csv.gz")
    assert set(diario["codigo"]) == {"A726"}
    catalogo = json.loads((tmp_path / "inmet" / "estacoes_sp.json").read_text("utf-8"))["estacoes"]
    assert [e["codigo"] for e in catalogo] == ["A726"]
    a726 = catalogo[0]
    # 31/12 só tem 20 h no pacote de 2024 (as 4 últimas, 21h–00h local, vêm no de 2025), mas passa do mínimo de 18 h
    assert a726["inicio_dados"] == "2024-01-01" and a726["fim_dados"] == "2024-12-31"
    assert diario.loc[diario["dia"] == "2024-12-31", "horas"].iloc[0] == 20

    # O pacote de 2025 completa o 31/12/2024
    script.atualizar_inmet([2025], forcar=False)
    diario = pd.read_csv(tmp_path / "inmet" / "diario" / "inmet_sp_2024.csv.gz")
    assert diario.loc[diario["dia"] == "2024-12-31", "horas"].iloc[0] == 24

    # Sem mudança no servidor, não baixa de novo
    n = len(baixados)
    script.atualizar_inmet([2024, 2025], forcar=False)
    assert len(baixados) == n


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


def test_ano_seguinte_parcial_nao_conta_como_baixado(script, monkeypatch, tmp_path):
    """O arquivo de 2025 traz a 1ª hora de 2026; isso não pode impedir o download de 2026."""
    baixados = []

    def falso_baixar(url, **_):
        baixados.append(url)
        return _arquivo_esalq("xlsx")

    monkeypatch.setattr(script, "baixar", falso_baixar)
    colunas = {"2025": {"baixado_em": "2026-01-10T10:00:00-03:00"}}
    assert script._ja_baixado(colunas, 2025)
    assert not script._ja_baixado(colunas, 2026)
    assert not script._ja_baixado({"2024": {"baixado_em": "2024-11-01T10:00:00-03:00"}}, 2024)


def test_recusa_arquivo_com_datas_fora_do_ano(script, monkeypatch, tmp_path):
    """Um arquivo antigo lido com a data errada não é gravado."""
    from tests.test_leitura import _arquivo_antigo

    monkeypatch.setattr(script, "baixar", lambda url, **_: _arquivo_antigo() if "2004" in url else None)
    script.atualizar_esalq([2004], desde=2004, forcar=True)  # o arquivo é de 2005
    assert not (tmp_path / "esalq" / "esalq_2004.csv.gz").exists()
    assert not (tmp_path / "esalq" / "esalq_2005.csv.gz").exists()

    monkeypatch.setattr(script, "baixar", lambda url, **_: _arquivo_antigo() if "2005" in url else None)
    script.atualizar_esalq([2005], desde=2005, forcar=True)
    df = pd.read_csv(tmp_path / "esalq" / "esalq_2005.csv.gz", parse_dates=["data_hora"])
    assert len(df) == 48 and df["chuva_mm"].sum() == pytest.approx(2.0)


def test_diario_refeito_preserva_dias_sem_horario(script, monkeypatch, tmp_path):
    """Refazer o diário de um ano a partir do horário não apaga estações que ainda não têm horário."""
    pasta = tmp_path / "inmet" / "diario"
    pasta.mkdir(parents=True)
    antigo = pd.DataFrame({"codigo": ["A999", "A999"], "dia": ["2023-06-01", "2023-06-02"],
                           "chuva_mm": [5.0, 0.0], "horas": [24, 24]})
    antigo.to_csv(pasta / "inmet_sp_2023.csv.gz", index=False)

    def falso_baixar(url, destino=None, **_):
        with zipfile.ZipFile(destino, "w") as z:
            z.writestr("2024/INMET_SE_SP_A726_PIRACICABA_01-01-2024_A_31-12-2024.CSV", _csv_inmet())
        return b""

    monkeypatch.setattr(script, "baixar", falso_baixar)
    script.atualizar_inmet([2024], forcar=True)  # mexe também em 2023 (31/12 local vem no pacote de 2024)
    d = pd.read_csv(pasta / "inmet_sp_2023.csv.gz")
    assert set(d["codigo"]) == {"A999", "A726"}
    assert d.loc[d["codigo"] == "A999", "chuva_mm"].tolist() == [5.0, 0.0]
