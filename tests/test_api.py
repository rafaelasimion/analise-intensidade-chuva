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


@pytest.fixture()
def inmet_horario(inmet_sintetico, tmp_path, monkeypatch):
    """Acrescenta dados horários (jan–fev/2024) à estação sintética A726."""
    pasta = tmp_path / "horario"
    monkeypatch.setattr(inmet, "DIR_INMET_HORARIO", pasta)
    inmet._ler_horario.cache_clear()
    t = pd.date_range("2024-01-01 01:00", "2024-03-01 00:00", freq="1h")
    chuva = np.zeros(len(t))
    chuva[(t >= "2024-01-10 15:00") & (t <= "2024-01-10 17:00")] = [12.0, 30.0, 6.0]  # evento de 48 mm
    h = pd.DataFrame({"data_hora": t, "chuva_mm": chuva, "temp_c": 24.0, "ur_pct": 80.0, "vento_ms": 2.0,
                      "vento_max_ms": 6.0, "rad_w_m2": np.where((t.hour >= 7) & (t.hour <= 18), 500.0, 0.0),
                      "pressao_hpa": 945.0})
    assert inmet.gravar_horario("A726", h) == {2024}
    yield
    inmet._ler_horario.cache_clear()


def test_posto_horario_do_inmet(inmet_horario):
    r = cliente.get("/api/posto/inmet-A726/meta")
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["posto"]["tem_registros"] and meta["posto"]["resolucao_min"] == 60
    assert meta["limites"]["inicio"].startswith("2024-01-01T01:00")

    # Período curto: o passo não fica mais fino que os dados (1 h, não 15 min)
    r = cliente.get("/api/posto/inmet-A726/painel", params={"inicio": "2024-01-10", "fim": "2024-01-11"})
    p = r.json()
    assert p["passo"] == "1h" and p["resumo"]["resolucao_min"] == 60
    assert p["resumo"]["chuva_total_mm"] == pytest.approx(48)
    assert p["resumo"]["intensidade_max"]["valor"] == pytest.approx(30)  # 30 mm em 1 h
    r = cliente.get("/api/posto/inmet-A726/painel", params={"inicio": "2024-01-10", "fim": "2024-01-11", "passo": "15min"})
    assert r.json()["passo"] == "1h"

    # Eventos: sem I15/I30 numa estação horária
    e = cliente.get("/api/posto/inmet-A726/eventos", params={"inicio": "2024-01-01", "fim": "2024-01-31"}).json()
    assert e["resumo"]["n_eventos"] == 1 and e["resumo"]["mais_intenso"]["coluna"] == "i60_mm_h"
    ev = e["eventos"][0]
    assert ev["i15_mm_h"] is None and ev["i60_mm_h"] == pytest.approx(30) and ev["duracao_min"] == 180

    m = cliente.get("/api/posto/inmet-A726/maximas", params={"inicio": "2024-01-01", "fim": "2024-02-29"}).json()
    assert m["duracoes_min"][0] == 60 and m["anos"][0]["valores"][0]["chuva_mm"] == pytest.approx(30)

    r = cliente.get("/api/posto/inmet-A726/relatorio", params={"inicio": "2024-01-01", "fim": "2024-02-29", "escala": "mensal"})
    linhas = r.json()["linhas"]
    assert [l["chuva_mm"] for l in linhas] == [pytest.approx(48), pytest.approx(0)]
    # radiação: 12 h × 500 W/m² = 21,6 MJ/m²
    assert linhas[0]["rad_mj_m2"] == pytest.approx(21.6)

    r = cliente.get("/api/posto/inmet-A726/download", params={"tipo": "dados", "formato": "csv_r",
                                                             "inicio": "2024-01-10", "fim": "2024-01-10"})
    assert r.status_code == 200 and r.content.startswith(b"data_hora,chuva_mm")
    assert "inmet_a726_dados" in r.headers["content-disposition"]


def test_posto_inmet_so_com_dados_diarios(inmet_sintetico):
    r = cliente.get("/api/posto/inmet-A726/painel", params={"inicio": "2024-01-01", "fim": "2024-03-31"})
    p = r.json()
    assert r.status_code == 200 and p["passo"] == "1D" and p["resumo"]["resolucao_min"] == 1440
    assert p["resumo"]["chuva_total_mm"] > 0
    assert cliente.get("/api/posto/inmet-A726/meta").json()["aviso"]


def test_mapa_e_comparacao(inmet_sintetico):
    r = cliente.get("/api/mapa", params={"inicio": "2024-01-01", "fim": "2024-12-31"})
    assert r.status_code == 200, r.text
    por_id = {p["id"]: p for p in r.json()["postos"]}
    assert por_id["inmet-A726"]["dias_com_dados"] == 366 and por_id["inmet-A726"]["chuva_mm"] > 500

    r = cliente.get("/api/comparar", params={"postos": "inmet-A726,esalq", "inicio": "2024-01", "fim": "2024-12"})
    assert r.status_code == 200, r.text
    c = r.json()
    assert [p["posto"]["id"] for p in c["postos"]] == ["inmet-A726", "esalq"]
    a726 = c["postos"][0]
    assert len(a726["mensal"]) == 12 and a726["totais"]["p_mm"] > 0
    assert c["distancias_km"]["km"][0][1] == pytest.approx(1.2, abs=0.3)
    corr = c["correlacao"]["chuva_mensal"]
    assert corr["r"][0][0] == 1.0

    assert cliente.get("/api/comparar", params={"postos": "esalq", "inicio": "2024-01", "fim": "2024-12"}).status_code == 400
    assert cliente.get("/api/posto/inmet-X000/painel").status_code == 404
