"""Eventos de chuva (chuva total, duração e intensidade em mm/h) e máximas anuais."""

from __future__ import annotations

import numpy as np
import pandas as pd

DURACOES_MAXIMAS_MIN = [15, 30, 60, 120, 180, 360, 720, 1440]


def _passo(df15: pd.DataFrame) -> pd.Timedelta:
    """Intervalo de registro mais comum (15 min na ESALQ, 1 h no INMET)."""
    dif = df15["data_hora"].sort_values().diff().dropna()
    dif = dif[(dif > pd.Timedelta(0)) & (dif <= pd.Timedelta(hours=3))]
    if dif.empty:
        return pd.Timedelta(minutes=15)
    return dif.mode().iloc[0]


def grade_chuva(df15: pd.DataFrame, passo: pd.Timedelta | None = None) -> tuple[pd.Series, pd.Timedelta]:
    """Chuva em grade regular (rótulo = fim do intervalo). Falhas ficam NaN."""
    passo = passo or _passo(df15)
    s = df15.set_index("data_hora")["chuva_mm"].sort_index()
    s = s.resample(passo, label="right", closed="right", origin="epoch").sum(min_count=1)
    return s, passo


def segmentos_por_passo(df15: pd.DataFrame) -> list[tuple[pd.DataFrame, pd.Timedelta]]:
    """Divide a série em trechos de anos seguidos com o mesmo intervalo de registro.

    Uma série que muda de resolução (p.ex. horária nos anos antigos e 15 min
    depois) não pode ir para uma grade só: a chuva de 1 h cairia num intervalo
    de 15 min e a intensidade sairia 4 vezes maior.
    """
    if df15.empty:
        return []
    ano = (df15["data_hora"] - pd.Timedelta(seconds=1)).dt.year
    passos = {int(a): _passo(parte) for a, parte in df15.groupby(ano)}
    segmentos, atual, inicio = [], None, None
    for a in sorted(passos):
        if passos[a] != atual:
            if atual is not None:
                segmentos.append((inicio, a - 1, atual))
            atual, inicio = passos[a], a
    segmentos.append((inicio, max(passos), atual))
    if len(segmentos) == 1:
        return [(df15, atual)]
    return [(df15[(ano >= a0) & (ano <= a1)], p) for a0, a1, p in segmentos]


def _somas_moveis(v: np.ndarray, k: int) -> np.ndarray:
    """Soma das k posições terminando em cada índice."""
    acum = np.concatenate([[0.0], np.cumsum(v)])
    fim = np.arange(1, len(v) + 1)
    ini = np.maximum(0, fim - k)
    return acum[fim] - acum[ini]


def eventos_chuva(df15: pd.DataFrame, intervalo_seco_h: float = 6.0, chuva_min_mm: float = 1.0) -> pd.DataFrame:
    """Separa eventos de chuva por um período seco mínimo.

    Para cada evento: início, fim, duração, chuva total, intensidade média
    (chuva ÷ duração, em mm/h) e intensidades máximas em 15, 30 e 60 min.
    """
    colunas = [
        "evento", "inicio", "fim", "duracao_min", "chuva_mm", "intensidade_media_mm_h",
        "i15_mm_h", "i30_mm_h", "i60_mm_h", "momento_pico", "registros_falhos",
    ]
    if df15.empty or df15["chuva_mm"].fillna(0).sum() <= 0:
        return pd.DataFrame(columns=colunas)

    partes = [_eventos_trecho(t, p, intervalo_seco_h, chuva_min_mm) for t, p in segmentos_por_passo(df15)]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(columns=colunas)
    tab = pd.concat(partes, ignore_index=True) if len(partes) > 1 else partes[0]
    tab.insert(0, "evento", np.arange(1, len(tab) + 1))
    return tab[colunas]


def _eventos_trecho(df15: pd.DataFrame, passo: pd.Timedelta, intervalo_seco_h: float, chuva_min_mm: float) -> pd.DataFrame:
    colunas = [
        "inicio", "fim", "duracao_min", "chuva_mm", "intensidade_media_mm_h",
        "i15_mm_h", "i30_mm_h", "i60_mm_h", "momento_pico", "registros_falhos",
    ]
    s, passo = grade_chuva(df15, passo)
    passo_h = passo.total_seconds() / 3600
    falhas = s.isna().to_numpy()
    v = s.fillna(0).to_numpy(dtype=float)
    tempos = s.index

    chuvosos = np.flatnonzero(v > 0)
    if chuvosos.size == 0:
        return pd.DataFrame(columns=colunas)
    passo_min = passo.total_seconds() / 60

    # Período seco entre o fim de um intervalo chuvoso e o início do próximo
    seco_h = (np.diff(chuvosos) - 1) * passo_h
    quebra = np.flatnonzero(seco_h >= intervalo_seco_h)
    inicios = np.concatenate([[chuvosos[0]], chuvosos[quebra + 1]])
    fins = np.concatenate([chuvosos[quebra], [chuvosos[-1]]])

    # Só as durações que são múltiplas do intervalo (numa estação horária não há I15 nem I30)
    k = {m: int(round(m / passo_min)) for m in (15, 30, 60)
         if m >= passo_min - 1e-9 and abs(m / passo_min - round(m / passo_min)) < 1e-6}
    moveis = {m: _somas_moveis(v, kk) for m, kk in k.items()}
    n = len(v)

    linhas = []
    for i0, i1 in zip(inicios, fins):
        total = float(v[i0:i1 + 1].sum())
        if total < chuva_min_mm:
            continue
        inicio = tempos[i0] - passo
        fim = tempos[i1]
        duracao_h = (fim - inicio).total_seconds() / 3600
        intens = {}
        for m, kk in k.items():
            j1 = min(i1 + kk - 1, n - 1)
            janela = moveis[m][i0:j1 + 1]
            intens[m] = float(janela.max()) / (kk * passo_h)
        pico = tempos[i0 + int(np.argmax(v[i0:i1 + 1]))]
        linhas.append({
            "inicio": inicio,
            "fim": fim,
            "duracao_min": round(duracao_h * 60),
            "chuva_mm": round(total, 3),
            "intensidade_media_mm_h": round(total / duracao_h, 3) if duracao_h > 0 else None,
            "i15_mm_h": round(intens[15], 3) if 15 in intens else np.nan,
            "i30_mm_h": round(intens[30], 3) if 30 in intens else np.nan,
            "i60_mm_h": round(intens[60], 3) if 60 in intens else np.nan,
            "momento_pico": pico,
            "registros_falhos": int(falhas[i0:i1 + 1].sum()),
        })

    return pd.DataFrame(linhas, columns=colunas)


def intensidade_simples(chuva_mm: float, duracao_min: float) -> float:
    """Intensidade média (mm/h) = chuva ÷ duração."""
    if duracao_min <= 0:
        raise ValueError("A duração deve ser maior que zero")
    return chuva_mm / (duracao_min / 60)


def maximas_anuais(df15: pd.DataFrame, duracoes_min: list[int] | None = None) -> dict:
    """Máxima chuva (e intensidade) de cada ano para várias durações (janelas móveis).

    É a série de entrada usual para ajuste de curvas IDF. Cada ano usa o seu
    intervalo de registro; durações menores que ele ficam vazias (None).
    """
    duracoes_min = duracoes_min or DURACOES_MAXIMAS_MIN
    if df15.empty:
        return {"duracoes_min": [], "anos": [], "estatisticas": []}

    anos = []
    usadas: set[int] = set()
    for trecho, passo in segmentos_por_passo(df15):
        s, passo = grade_chuva(trecho, passo)
        passo_min = passo.total_seconds() / 60
        validas = {d for d in duracoes_min
                   if d >= passo_min - 1e-9 and abs(d / passo_min - round(d / passo_min)) < 1e-6}
        usadas |= validas
        falhas = s.isna()
        v = s.fillna(0)
        dias = (s.index - pd.Timedelta(seconds=1)).normalize()
        diario = v.groupby(dias).sum().where(s.groupby(dias).count() > 0)
        ano_de = (s.index - pd.Timedelta(seconds=1)).year

        for ano in sorted(set(ano_de)):
            mascara = ano_de == ano
            va = v[mascara]
            if va.empty:
                continue
            esperado = (pd.Timestamp(f"{ano + 1}-01-01") - pd.Timestamp(f"{ano}-01-01")) / passo
            cobertura = float((~falhas[mascara]).sum() / esperado * 100)
            arr = va.to_numpy(dtype=float)
            valores = []
            for d in duracoes_min:
                if d not in validas:
                    valores.append({"duracao_min": d, "chuva_mm": None, "intensidade_mm_h": None, "quando": None})
                    continue
                kk = int(round(d / passo_min))
                somas = _somas_moveis(arr, kk)
                j = int(np.argmax(somas))
                total = float(somas[j])
                valores.append({
                    "duracao_min": d,
                    "chuva_mm": round(total, 2),
                    "intensidade_mm_h": round(total / (d / 60), 2),
                    "quando": va.index[j].isoformat() if total > 0 else None,
                })
            da = diario[diario.index.year == ano].dropna()
            anos.append({
                "ano": int(ano),
                "intervalo_min": int(round(passo_min)),
                "cobertura_pct": round(min(cobertura, 100.0), 1),
                "chuva_total_mm": round(float(va.sum()), 1),
                "chuva_max_dia_mm": round(float(da.max()), 2) if not da.empty else None,
                "data_chuva_max_dia": da.idxmax().date().isoformat() if not da.empty else None,
                "valores": valores,
            })

    # Só as durações calculáveis em algum ano
    duracoes = [d for d in duracoes_min if d in usadas]
    for a in anos:
        a["valores"] = [v for v in a["valores"] if v["duracao_min"] in usadas]

    # Estatísticas das máximas (só anos com ≥ 80% de dados)
    completos = [a for a in anos if a["cobertura_pct"] >= 80]
    estat = []
    for i, d in enumerate(duracoes):
        xs = np.array([a["valores"][i]["intensidade_mm_h"] for a in completos
                       if a["valores"][i]["intensidade_mm_h"] is not None], dtype=float)
        estat.append({
            "duracao_min": d,
            "n_anos": int(len(xs)),
            "media_mm_h": round(float(xs.mean()), 2) if len(xs) else None,
            "desvio_padrao_mm_h": round(float(xs.std(ddof=1)), 2) if len(xs) > 1 else None,
            "maxima_mm_h": round(float(xs.max()), 2) if len(xs) else None,
        })
    return {"duracoes_min": duracoes, "anos": anos, "estatisticas": estat}


def maximas_para_tabela(maximas: dict) -> pd.DataFrame:
    """Formato largo (um ano por linha) para planilhas."""
    linhas = []
    for a in maximas["anos"]:
        linha = {
            "ano": a["ano"],
            "intervalo_min": a.get("intervalo_min"),
            "cobertura_pct": a["cobertura_pct"],
            "chuva_total_mm": a["chuva_total_mm"],
            "chuva_max_dia_mm": a["chuva_max_dia_mm"],
            "data_chuva_max_dia": a["data_chuva_max_dia"],
        }
        for v in a["valores"]:
            d = v["duracao_min"]
            linha[f"p_{d}min_mm"] = v["chuva_mm"]
            linha[f"i_{d}min_mm_h"] = v["intensidade_mm_h"]
        linhas.append(linha)
    return pd.DataFrame(linhas)
