"""API (FastAPI) – roda como função Python da Vercel em /api/*.

Documentação interativa: /api/docs
Local:  uvicorn api.index:app --reload --port 8000
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from hidro import __version__, armazenamento, fontes  # noqa: E402
from hidro import agregacao as ag  # noqa: E402
from hidro import eventos as ev  # noqa: E402
from hidro import exportar as ex  # noqa: E402
from hidro.balanco import calcular_balanco  # noqa: E402
from hidro.config import DIR_DADOS, ESALQ, VARIAVEIS  # noqa: E402

app = FastAPI(
    title="Análise hidrológica – ESALQ e postos de SP",
    version=__version__,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)


# ---------------------------------------------------------------------------
# A Vercel reescreve /api/<rota> para esta função. Se o caminho original não
# chegar até aqui, ele é reconstruído pelo parâmetro __rota (ver vercel.json).
# ---------------------------------------------------------------------------
class _CorrigeCaminho:
    def __init__(self, asgi_app):
        self.app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "") in ("/api/index", "/api/index.py", "/api", "/api/"):
            qs = parse_qs(scope.get("query_string", b"").decode())
            rota = qs.get("__rota", [None])[0]
            if rota:
                caminho = "/api/" + rota.lstrip("/")
                scope = {**scope, "path": caminho, "raw_path": caminho.encode()}
        await self.app(scope, receive, send)


app.add_middleware(_CorrigeCaminho)

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

CACHE_CURTO = "public, max-age=60, s-maxage=600, stale-while-revalidate=3600"


def _limpo(obj: Any) -> Any:
    """Converte para tipos JSON (NaN/inf -> None, datas -> ISO)."""
    if isinstance(obj, dict):
        return {str(k): _limpo(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_limpo(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return ag.tabela_para_json(obj)
    if obj is None or obj is pd.NaT:
        return None
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    if isinstance(obj, pd.Period):
        return str(obj)
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    return obj


def _resposta(dados: Any, cache: bool = True) -> JSONResponse:
    return JSONResponse(
        _limpo(dados),
        headers={"Cache-Control": CACHE_CURTO if cache else "no-store"},
    )


def _data(texto: str | None, nome: str) -> date | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(texto[:10])
    except ValueError as exc:
        raise HTTPException(400, f"Data inválida em '{nome}': use AAAA-MM-DD") from exc


def _periodo(inicio: str | None, fim: str | None, padrao_dias: int = 30) -> tuple[date, date]:
    fi = _data(fim, "fim")
    ini = _data(inicio, "inicio")
    if fi is None:
        lim = armazenamento.limites_dados()
        fi = date.fromisoformat(lim["fim"][:10]) if lim["fim"] else armazenamento.hoje()
    if ini is None:
        ini = fi - timedelta(days=padrao_dias - 1)
    if ini > fi:
        ini, fi = fi, ini
    if (fi - ini).days > 366 * 60:
        raise HTTPException(400, "Período muito longo (máximo 60 anos)")
    return ini, fi


def _arquivo(conteudo: bytes, nome: str, tipo: str) -> StreamingResponse:
    """Download em blocos (respostas em streaming não têm o limite de 4,5 MB da Vercel)."""
    def blocos():
        for i in range(0, len(conteudo), 256 * 1024):
            yield conteudo[i:i + 256 * 1024]
    return StreamingResponse(
        blocos(),
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store"},
    )


FORMATOS = {
    "csv_r": ("text/csv; charset=utf-8", "csv"),
    "csv_excel": ("text/csv; charset=utf-8", "csv"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
}


def _exportar(df: pd.DataFrame, formato: str, nome_base: str, aba: str, leia_me=None) -> StreamingResponse:
    if formato not in FORMATOS:
        raise HTTPException(400, "Formato inválido (use csv_r, csv_excel ou xlsx)")
    df = ex.limpar_para_planilha(df)
    tipo, ext = FORMATOS[formato]
    if formato == "csv_r":
        return _arquivo(ex.csv_r(df), f"{nome_base}_R.{ext}", tipo)
    if formato == "csv_excel":
        return _arquivo(ex.csv_excel(df), f"{nome_base}_excel.{ext}", tipo)
    return _arquivo(ex.xlsx([(aba, df)], leia_me), f"{nome_base}.{ext}", tipo)


def _erro(exc: Exception) -> HTTPException:
    return HTTPException(400, str(exc))


COLUNAS_TABELA_15MIN = [
    "data_hora", "chuva_mm", "intensidade_mm_h", "chuva_acum_dia_mm", "temp_c", "temp_max_c", "temp_min_c",
    "ur_pct", "vento_ms", "vento_max_ms", "vento_dir_graus", "rad_w_m2", "pressao_hpa",
]


def _so_com_dados(df: pd.DataFrame, colunas: list[str], sempre: tuple[str, ...] = ("data_hora", "chuva_mm")) -> list[str]:
    return [c for c in colunas if c in df and (c in sempre or df[c].notna().any())]


def _leia_me_base(titulo: str, ini: date, fim: date, extra: list[tuple[str, str]] | None = None):
    itens = [
        ("Conteúdo", titulo),
        ("Estação", f"{ESALQ['nome']} – {ESALQ['municipio']}/SP ({ESALQ['lat']}, {ESALQ['lon']}, {ESALQ['alt']:.0f} m)"),
        ("Período", f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}"),
        ("Fonte dos dados", ESALQ["fonte"]),
        ("Gerado em", ex.gerado_em()),
        ("Convenção de horário", "Cada registro de 15 min representa o intervalo que TERMINA no horário indicado; "
                                 "o registro de 00:00 pertence ao dia anterior."),
        ("Intensidade", "Intensidade (mm/h) = chuva do intervalo ÷ duração do intervalo (h)."),
        ("Dia com chuva", "Dia com chuva ≥ 1 mm (critério da OMM)."),
        ("Falhas", "Células vazias = sem dado válido (falha do sensor ou valor descartado na limpeza)."),
    ]
    return itens + (extra or [])


# ---------------------------------------------------------------------------
# Rotas gerais
# ---------------------------------------------------------------------------


@app.get("/api/saude")
def saude():
    return _resposta({"ok": True, "versao": __version__}, cache=False)


@app.get("/api/esalq/meta")
def esalq_meta(atualizar: bool = False):
    """Anos disponíveis, primeiro/último registro e situação do ano corrente."""
    ano = armazenamento.hoje().year
    df_atual, meta_atual = armazenamento.carregar_ano(ano, atualizar=atualizar)
    atualizacao = {}
    arq = DIR_DADOS / "atualizacao.json"
    if arq.exists():
        try:
            atualizacao = json.loads(arq.read_text("utf-8"))
        except ValueError:
            pass
    return _resposta({
        "estacao": ESALQ,
        "anos": armazenamento.anos_disponiveis(),
        "limites": armazenamento.limites_dados(),
        "ano_atual": meta_atual,
        "variaveis_ano_atual": ag.variaveis_com_dados(df_atual),
        "variaveis": {k: {"rotulo": v[0], "unidade": v[1]} for k, v in VARIAVEIS.items()},
        "atualizacao_repositorio": atualizacao,
    }, cache=not atualizar)


@app.get("/api/esalq/diagnostico")
def esalq_diagnostico():
    """Colunas encontradas nos arquivos da ESALQ e como foram interpretadas."""
    return _resposta({"arquivos": armazenamento.info_colunas()}, cache=False)


@app.get("/api/esalq/painel")
def esalq_painel(inicio: str | None = None, fim: str | None = None, passo: str = "auto"):
    ini, fi = _periodo(inicio, fim)
    df15, metas = armazenamento.carregar_15min(ini, fi)
    diario = ag.diario_de_15min(df15)
    if passo == "auto":
        passo = ag.escolher_passo(ini, fi)
    if passo not in ag.PASSOS:
        raise HTTPException(400, "passo inválido")
    s = ag.serie(df15, diario, passo) if not df15.empty else pd.DataFrame({"t": []})
    return _resposta({
        "resumo": ag.resumo(df15, diario, ini, fi),
        "passo": passo,
        "serie": ag.serie_para_json(s) if not df15.empty else {"t": []},
        "origem": metas,
    })


@app.get("/api/esalq/dados")
def esalq_dados(
    inicio: str | None = None, fim: str | None = None,
    pagina: int = Query(1, ge=1), por_pagina: int = Query(100, ge=10, le=1000),
    so_chuva: bool = False, ordem: str = "desc",
):
    ini, fi = _periodo(inicio, fim, 7)
    df15, _ = armazenamento.carregar_15min(ini, fi)
    if so_chuva:
        df15 = df15[df15["chuva_mm"] > 0]
    df15 = df15.sort_values("data_hora", ascending=(ordem == "asc"))
    colunas = _so_com_dados(df15, COLUNAS_TABELA_15MIN)
    total = len(df15)
    pagina_df = df15.iloc[(pagina - 1) * por_pagina: pagina * por_pagina][colunas]
    return _resposta({
        "total": total, "pagina": pagina, "por_pagina": por_pagina,
        "paginas": max(1, math.ceil(total / por_pagina)),
        "colunas": colunas,
        "linhas": ag.tabela_para_json(pagina_df),
    })


@app.get("/api/esalq/eventos")
def esalq_eventos(
    inicio: str | None = None, fim: str | None = None,
    intervalo_seco_h: float = Query(6.0, gt=0, le=72), chuva_min_mm: float = Query(1.0, ge=0),
):
    ini, fi = _periodo(inicio, fim, 90)
    df15, _ = armazenamento.carregar_15min(ini, fi)
    tab = ev.eventos_chuva(df15, intervalo_seco_h, chuva_min_mm)
    resumo = {"n_eventos": int(len(tab))}
    if len(tab):
        maior = tab.loc[tab["chuva_mm"].idxmax()]
        intenso = tab.loc[tab["i15_mm_h"].idxmax()]
        resumo.update({
            "chuva_total_eventos_mm": round(float(tab["chuva_mm"].sum()), 2),
            "duracao_media_min": round(float(tab["duracao_min"].mean())),
            "maior_evento": {"evento": int(maior["evento"]), "chuva_mm": float(maior["chuva_mm"]),
                             "inicio": maior["inicio"]},
            "mais_intenso": {"evento": int(intenso["evento"]), "i15_mm_h": float(intenso["i15_mm_h"]),
                             "inicio": intenso["inicio"]},
        })
    return _resposta({
        "parametros": {"inicio": ini, "fim": fi, "intervalo_seco_h": intervalo_seco_h, "chuva_min_mm": chuva_min_mm},
        "resumo": resumo,
        "eventos": ag.tabela_para_json(tab),
    })


@app.get("/api/esalq/relatorio")
def esalq_relatorio(inicio: str | None = None, fim: str | None = None, escala: str = "mensal"):
    ini, fi = _periodo(inicio, fim, 365)
    if escala == "diario" and (fi - ini).days > 366 * 20:
        raise HTTPException(400, "O relatório diário aceita até 20 anos; use o semanal, mensal ou anual")
    df15, metas = armazenamento.carregar_15min(ini, fi)
    diario = ag.diario_de_15min(df15)
    try:
        tab = ag.relatorio(diario, df15, escala)
    except ValueError as exc:
        raise _erro(exc) from exc
    colunas = [c for c in tab.columns if c in ("periodo", "inicio", "fim", "chuva_mm") or tab[c].notna().any()]
    return _resposta({
        "escala": escala,
        "resumo": ag.resumo(df15, diario, ini, fi),
        "colunas": colunas,
        "linhas": ag.tabela_para_json(tab[colunas]) if len(tab) else [],
        "origem": metas,
    })


@app.get("/api/esalq/maximas")
def esalq_maximas(inicio: str | None = None, fim: str | None = None):
    ini, fi = _periodo(inicio, fim, 365 * 30)
    df15, _ = armazenamento.carregar_15min(ini, fi)
    return _resposta(ev.maximas_anuais(df15))


@app.get("/api/esalq/download")
def esalq_download(
    tipo: str = "dados", formato: str = "csv_r",
    inicio: str | None = None, fim: str | None = None, so_chuva: bool = False,
    intervalo_seco_h: float = 6.0, chuva_min_mm: float = 1.0,
):
    ini, fi = _periodo(inicio, fim, 30)
    df15, _ = armazenamento.carregar_15min(ini, fi)
    base = f"esalq_{tipo}_{ini:%Y%m%d}_{fi:%Y%m%d}"
    if tipo == "dados":
        if so_chuva:
            df15 = df15[df15["chuva_mm"] > 0]
        tab = df15[_so_com_dados(df15, COLUNAS_TABELA_15MIN)]
        aba = "Dados 15 min"
    elif tipo in ("diario", "semanal", "mensal", "anual"):
        tab = ag.relatorio(ag.diario_de_15min(df15), df15, tipo)
        tab = tab[[c for c in tab.columns if c in ("periodo", "inicio", "fim", "chuva_mm") or tab[c].notna().any()]]
        aba = {"diario": "Diário", "semanal": "Semanal", "mensal": "Mensal", "anual": "Anual"}[tipo]
    elif tipo == "eventos":
        tab = ev.eventos_chuva(df15, intervalo_seco_h, chuva_min_mm)
        aba = "Eventos de chuva"
    elif tipo == "maximas":
        tab = ev.maximas_para_tabela(ev.maximas_anuais(df15))
        aba = "Máximas anuais"
    else:
        raise HTTPException(400, "tipo inválido")
    if formato == "xlsx" and len(tab) > 300_000:
        raise HTTPException(400, "Período longo demais para .xlsx (mais de 300 mil linhas); baixe em CSV")
    leia_me = _leia_me_base(aba, ini, fi)
    return _exportar(tab, formato, base, aba, leia_me)


@app.get("/api/esalq/planilha")
def esalq_planilha(inicio: str | None = None, fim: str | None = None,
                   intervalo_seco_h: float = 6.0, chuva_min_mm: float = 1.0, cad: float = 100.0):
    """Planilha hidrológica completa (.xlsx com várias abas)."""
    ini, fi = _periodo(inicio, fim, 365)
    df15, _ = armazenamento.carregar_15min(ini, fi)
    if df15.empty:
        raise HTTPException(404, "Sem dados no período")
    diario = ag.diario_de_15min(df15)

    def sem_vazias(t: pd.DataFrame) -> pd.DataFrame:
        return t[[c for c in t.columns if c in ("periodo", "inicio", "fim", "chuva_mm") or t[c].notna().any()]]

    abas = [
        ("Diário", sem_vazias(ag.relatorio(diario, df15, "diario"))),
        ("Semanal", sem_vazias(ag.relatorio(diario, df15, "semanal"))),
        ("Mensal", sem_vazias(ag.relatorio(diario, df15, "mensal"))),
        ("Anual", sem_vazias(ag.relatorio(diario, df15, "anual"))),
        ("Eventos de chuva", ev.eventos_chuva(df15, intervalo_seco_h, chuva_min_mm)),
        ("Máximas anuais", ev.maximas_para_tabela(ev.maximas_anuais(df15))),
    ]
    extra = [
        ("Eventos de chuva", f"Separados por ≥ {intervalo_seco_h:g} h sem chuva; só eventos com ≥ {chuva_min_mm:g} mm. "
                             "Intensidade média = chuva total ÷ duração; I15/I30/I60 = maiores intensidades "
                             "em janelas móveis de 15, 30 e 60 min."),
        ("Máximas anuais", "Maior chuva de cada ano em janelas móveis de 15 min a 24 h (base para curvas IDF). "
                           "Anos com cobertura < 80% devem ser usados com cuidado."),
    ]
    # Balanço hídrico mensal, se houver temperatura
    if diario["temp_c"].notna().sum() > 300:
        try:
            todo = armazenamento.carregar_diario_esalq()
            ini_p, fim_p = pd.Period(ini, "M"), pd.Period(fi, "M")
            bh = calcular_balanco(todo, ESALQ["lat"], ini_p, fim_p, cad, "mensal")
            abas.append(("Balanço hídrico", bh["sequencial"]))
            abas.append(("BH normal", pd.DataFrame(bh["normal"])))
            extra.append(("Balanço hídrico", f"Thornthwaite & Mather (1955), ETP de Thornthwaite (1948), CAD = {cad:g} mm."))
        except ValueError as exc:
            extra.append(("Balanço hídrico", f"Não calculado: {exc}"))
    else:
        extra.append(("Balanço hídrico", "Não calculado: o período não tem dados de temperatura suficientes."))

    if len(df15) <= 70_000:
        abas.insert(0, ("Dados 15 min", df15[_so_com_dados(df15, COLUNAS_TABELA_15MIN)]))
    else:
        extra.append(("Dados 15 min", "Período longo demais para a planilha: baixe os dados de 15 min em CSV."))

    conteudo = ex.xlsx([(n, ex.limpar_para_planilha(t)) for n, t in abas],
                       _leia_me_base("Planilha hidrológica", ini, fi, extra))
    return _arquivo(conteudo, f"planilha_hidrologica_esalq_{ini:%Y%m%d}_{fi:%Y%m%d}.xlsx", FORMATOS["xlsx"][0])


# ---------------------------------------------------------------------------
# Postos e balanço hídrico
# ---------------------------------------------------------------------------


@app.get("/api/postos")
def postos(busca: str = ""):
    return _resposta({"postos": fontes.lista_postos(busca)})


def _executar_balanco(fonte, codigo, lat, lon, inicio, fim, cad, escala):
    try:
        ini_p = pd.Period(inicio, "M")
        fim_p = pd.Period(fim, "M")
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Use inicio e fim no formato AAAA-MM") from exc
    if fim_p < ini_p:
        ini_p, fim_p = fim_p, ini_p
    if (fim_p - ini_p).n > 12 * 60:
        raise HTTPException(400, "Período muito longo (máximo 60 anos)")
    if not 1 <= cad <= 1000:
        raise HTTPException(400, "CAD deve estar entre 1 e 1000 mm")
    if escala == "diario" and (fim_p - ini_p).n + 1 > 240:
        raise HTTPException(400, "O passo diário aceita até 20 anos; para períodos maiores, use o passo mensal")
    try:
        diario, info = fontes.dados_para_balanco(fonte, ini_p.start_time.date(), fim_p.end_time.date(), codigo, lat, lon)
        res = calcular_balanco(diario, float(info["lat"]), ini_p, fim_p, cad, escala)
    except ValueError as exc:
        raise _erro(exc) from exc
    except Exception as exc:  # noqa: BLE001 - p.ex. falha de rede no NASA POWER
        raise HTTPException(502, f"Falha ao obter os dados ({type(exc).__name__}): {exc}") from exc
    return info, res


@app.get("/api/balanco")
def balanco(
    fonte: str = "esalq", codigo: str | None = None, lat: float | None = None, lon: float | None = None,
    inicio: str = Query(..., description="AAAA-MM"), fim: str = Query(..., description="AAAA-MM"),
    cad: float = 100.0, escala: str = "mensal",
):
    info, res = _executar_balanco(fonte, codigo, lat, lon, inicio, fim, cad, escala)
    res["sequencial"] = ag.tabela_para_json(res["sequencial"])
    res["sequencial_mensal"] = ag.tabela_para_json(res["sequencial_mensal"]) if escala == "diario" else None
    return _resposta({"posto": info, **res})


@app.get("/api/balanco/download")
def balanco_download(
    fonte: str = "esalq", codigo: str | None = None, lat: float | None = None, lon: float | None = None,
    inicio: str = Query(...), fim: str = Query(...), cad: float = 100.0, escala: str = "mensal",
    formato: str = "xlsx",
):
    info, res = _executar_balanco(fonte, codigo, lat, lon, inicio, fim, cad, escala)
    base = f"balanco_hidrico_{(info.get('codigo') or info['fonte']).lower()}_{inicio}_{fim}_cad{cad:g}"
    seq = res["sequencial"]
    if formato != "xlsx":
        return _exportar(seq, formato, base, "Balanço sequencial")
    idx = res["indices"]
    leia_me = [
        ("Conteúdo", "Balanço hídrico climatológico"),
        ("Posto", f"{info['nome']} ({info.get('codigo') or '-'}) – lat {info['lat']}, lon {info['lon']}"),
        ("Fonte dos dados", info["descricao_fonte"]),
        ("Período", f"{res['parametros']['inicio']} a {res['parametros']['fim']} ({escala})"),
        ("Método", res["parametros"]["metodo"]),
        ("CAD", f"{cad:g} mm"),
        ("Índice de calor", f"I = {res['indice_calor']['I']}, a = {res['indice_calor']['a']}"),
        ("Normais", f"Calculadas com dados de {res['base_normais']['inicio']} a {res['base_normais']['fim']}"),
        ("ARM inicial", f"{res['parametros']['arm_inicial_mm']} mm (do balanço normal, mês anterior ao início)"),
        ("Classificação (normal)", f"Im = {idx['indice_hidrico_im']} → {idx['tipo_climatico']} ({idx['descricao']}); "
                                   f"Ih = {idx['indice_umidade_ih']}, Ia = {idx['indice_aridez_ia']}"),
        ("Avisos", " ".join(res["avisos"]) or "—"),
        ("Gerado em", ex.gerado_em()),
    ]
    abas = [("Sequencial", seq)]
    if escala == "diario":
        abas.append(("Resumo mensal", res["sequencial_mensal"]))
    abas += [("Normal", pd.DataFrame(res["normal"])), ("Normais", pd.DataFrame(res["normais"]))]
    conteudo = ex.xlsx([(n, ex.limpar_para_planilha(t)) for n, t in abas], leia_me)
    return _arquivo(conteudo, f"{base}.xlsx", FORMATOS["xlsx"][0])
