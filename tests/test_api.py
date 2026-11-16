import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import hidro.inmet as inmet
from api.index import app

cliente = TestClient(app)


@pytest.fixture()
def inmet_sintetico(tmp_path, monkeypatch):
    """Cria uma estação do INMET com 6 anos de dados diários sintéticos."""
    pasta = tmp_path / "diario"
    pasta.mkdir()
    monkeypatch.setattr(inmet, "DIR_INMET_DIARIO", pasta)
    monkeypatch.setattr(inmet, "ARQ_ESTACOES", tmp_path / "estacoes_sp.json")
    inmet._ler_ano.cache_clear()
    (tmp_path / "estacoes_sp.json").write_text(json.dumps({"estacoes": [{
        "codigo": "A726", "nome": "PIRACICABA", "uf": "SP", "lat": -22.703, "lon": -47.623, "alt": 566,
        "inicio_dados": "2019-01-01", "fim_dados": "2024-12-31",
    }]}), "utf-8")
    rng = np.random.default_rng(0)
    t_norm = [24.1, 24.4, 23.8, 21.9, 19.2, 17.8, 17.4, 19.4, 20.9, 22.3, 23.1, 23.6]
    p_norm = [230, 185, 150, 65, 55, 45, 30, 30, 60, 120, 140, 205]
    for ano in range(2019, 2025):
        dias = pd.date_range(f"{ano}-01-01", f"{ano}-12-31")
        m = dias.month - 1
        df = pd.DataFrame({
            "codigo": "A726", "dia": dias,
            "chuva_mm": np.where(rng.random(len(dias)) < 0.3, np.array(p_norm)[m] / dias.days_in_month / 0.3, 0),
            "temp_c": np.array(t_norm)[m] + rng.normal(0, 1, len(dias)),
        })
        for c in inmet.COLUNAS_DIARIO:
            if c not in df:
                df[c] = np.nan
        df[inmet.COLUNAS_DIARIO].to_csv(pasta / f"inmet_sp_{ano}.csv.gz", index=False)
    yield
    inmet._ler_ano.cache_clear()


def test_meta_e_painel():
    r = cliente.get("/api/esalq/meta")
    assert r.status_code == 200
    anos = r.json()["anos"]
    assert anos and min(anos) <= 2025
    r = cliente.get("/api/esalq/painel", params={"inicio": "2025-01-01", "fim": "2025-01-31"})
    corpo = r.json()
    assert r.status_code == 200 and corpo["passo"] == "1h"
    assert corpo["resumo"]["chuva_total_mm"] > 0
    assert len(corpo["serie"]["t"]) == len(corpo["serie"]["chuva_mm"])


def test_rotas_com_vercel_reescrevendo_caminho():
    r = cliente.get("/api/index", params={"__rota": "esalq/eventos", "inicio": "2025-01-01", "fim": "2025-01-31"})
    assert r.status_code == 200 and "eventos" in r.json()


def test_downloads():
    for formato, inicio in (("csv_r", b"data_hora,chuva_mm"), ("csv_excel", "Data/hora;Chuva (mm)".encode("utf-8-sig"))):
        r = cliente.get("/api/esalq/download", params={"tipo": "dados", "formato": formato,
                                                        "inicio": "2025-01-01", "fim": "2025-01-02"})
        assert r.status_code == 200 and r.content.startswith(inicio)
    r = cliente.get("/api/esalq/planilha", params={"inicio": "2025-01-01", "fim": "2025-02-28"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    abas = pd.ExcelFile(__import__("io").BytesIO(r.content)).sheet_names
    assert {"Leia-me", "Dados 15 min", "Diário", "Mensal", "Eventos de chuva", "Máximas anuais"} <= set(abas)


def test_erros_de_parametro():
    assert cliente.get("/api/esalq/painel", params={"inicio": "2025-13-01"}).status_code == 400
    assert cliente.get("/api/esalq/relatorio", params={"escala": "quinzenal"}).status_code == 400
    assert cliente.get("/api/balanco", params={"inicio": "2025-01", "fim": "2025-12", "cad": 0}).status_code == 400


def test_balanco_inmet(inmet_sintetico):
    r = cliente.get("/api/balanco", params={"fonte": "inmet", "codigo": "A726", "inicio": "2020-01",
                                           "fim": "2024-12", "cad": 100})
    assert r.status_code == 200, r.text
    b = r.json()
    assert len(b["sequencial"]) == 60
    assert b["posto"]["codigo"] == "A726"
    assert 900 < b["totais_normal"]["etp_mm"] < 1200
    assert b["indices"]["tipo_climatico"]

    r = cliente.get("/api/balanco", params={"fonte": "inmet", "codigo": "A726", "inicio": "2024-02",
                                           "fim": "2024-02", "escala": "diario"})
    assert r.status_code == 200 and len(r.json()["sequencial"]) == 29

    r = cliente.get("/api/balanco/download", params={"fonte": "inmet", "codigo": "A726", "inicio": "2020-01",
                                                    "fim": "2024-12", "formato": "xlsx"})
    assert r.status_code == 200
    abas = pd.ExcelFile(__import__("io").BytesIO(r.content)).sheet_names
    assert abas[:3] == ["Leia-me", "Sequencial", "Normal"]

    r = cliente.get("/api/postos", params={"busca": "pira"})
    assert any(p["codigo"] == "A726" for p in r.json()["postos"])
