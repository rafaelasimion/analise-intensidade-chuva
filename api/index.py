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

from hidro import __version__, armazenamento, fontes, inmet, postos  # noqa: E402
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


def _posto(pid: str) -> dict:
    try:
        return postos.obter(pid)
    except postos.PostoDesconhecido as exc:
        raise HTTPException(404, str(exc)) from exc


def _periodo_posto(pid: str, inicio: str | None, fim: str | None, padrao_dias: int = 30) -> tuple[date, date]:
    _posto(pid)  # 404 se o posto não existir
    fi = _data(fim, "fim")
    ini = _data(inicio, "inicio")
    if fi is None:
        lim = postos.limites(pid)
        # O último registro (00:00) pertence ao dia anterior
        fi = (pd.Timestamp(lim["fim"]) - pd.Timedelta(seconds=1)).date() if lim["fim"] else armazenamento.hoje()
    if ini is None:
        ini = fi - timedelta(days=padrao_dias - 1)
    if ini > fi:
        ini, fi = fi, ini
    if (fi - ini).days > 366 * 60:
        raise HTTPException(400, "Período muito longo (máximo 60 anos)")
    return ini, fi


def _carregar(pid: str, ini: date, fi: date, atualizar: bool = False):
    """(registros, diário, origem, info do posto). Sem dados horários, usa só o diário."""
    info = _posto(pid)
    df15, metas = postos.carregar_registros(info["id"], ini, fi, atualizar)
    if df15.empty and not info["tem_registros"] and info["tem_dados"]:
        diario = postos.carregar_diario(info["id"], ini, fi)
    else:
        diario = ag.diario_de_15min(df15)
    return df15, diario, metas, info


def _sem_vazias(t: pd.DataFrame) -> pd.DataFrame:
    return t[[c for c in t.columns if c in ("periodo", "inicio", "fim", "chuva_mm") or t[c].notna().any()]]


def _nome_arquivo(info: dict) -> str:
    return "esalq" if info["fonte"] == "esalq" else f"inmet_{info['codigo'].lower()}"


def _leia_me_base(info: dict, titulo: str, ini: date, fim: date, extra: list[tuple[str, str]] | None = None):
    alt = f", {info['alt']:.0f} m" if info.get("alt") is not None else ""
    if info["fonte"] == "esalq":
        horario = ("Hora local de Brasília (UTC−3). Cada registro de 15 min representa o intervalo que TERMINA no "
                   "horário indicado; o registro de 00:00 pertence ao dia anterior.")
        fonte = ESALQ["fonte"]
    else:
        horario = ("O INMET publica em UTC; aqui os horários estão em hora local de Brasília (UTC−3). Cada registro "
                   "horário representa a hora que TERMINA no horário indicado; o de 00:00 pertence ao dia anterior.")
        fonte = f"INMET – estação automática {info['codigo']} ({info['url_fonte']})"
    itens = [
        ("Conteúdo", titulo),
        ("Posto", f"{info['nome']} ({info['codigo']}) – {info.get('municipio') or ''}/SP ({info['lat']}, {info['lon']}{alt})"),
        ("Período", f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}"),
        ("Fonte dos dados", fonte),
        ("Gerado em", ex.gerado_em()),
        ("Convenção de horário", horario),
        ("Intensidade", "Intensidade (mm/h) = chuva do intervalo ÷ duração do intervalo (h)."),
        ("Dia com chuva", "Dia com chuva ≥ 1 mm (critério da OMM)."),
        ("Falhas", "Células vazias = sem dado válido (falha do sensor ou valor descartado na limpeza)."),
    ]
    return itens + (extra or [])


def _ler_atualizacao() -> dict:
    arq = DIR_DADOS / "atualizacao.json"
    if arq.exists():
        try:
            return json.loads(arq.read_text("utf-8"))
        except ValueError:
            pass
    return {}


# ---------------------------------------------------------------------------
# Rotas gerais
# ---------------------------------------------------------------------------


@app.get("/api/saude")
def saude():
    return _resposta({"ok": True, "versao": __version__}, cache=False)


@app.get("/api/esalq/diagnostico")
def esalq_diagnostico():
    """Colunas encontradas nos arquivos da ESALQ e como foram interpretadas."""
    return _resposta({"arquivos": armazenamento.info_colunas()}, cache=False)


# ---------------------------------------------------------------------------
# Um posto (ESALQ ou INMET): /api/posto/<id>/...   (id = "esalq" ou "inmet-A711")
# As rotas antigas /api/esalq/... continuam valendo.
# ---------------------------------------------------------------------------


@app.get("/api/posto/{pid}/meta")
def posto_meta(pid: str, atualizar: bool = False):
    """Informações do posto, anos e primeiro/último registro."""
    info = _posto(pid)
    resposta = {
        "posto": info,
        "anos": postos.anos(info["id"]),
        "variaveis": {k: {"rotulo": v[0], "unidade": v[1]} for k, v in VARIAVEIS.items()},
        "atualizacao_repositorio": _ler_atualizacao(),
    }
    if info["fonte"] == "esalq":
        ano = armazenamento.hoje().year
        df_atual, meta_atual = armazenamento.carregar_ano(ano, atualizar=atualizar)
        resposta.update({
            "estacao": ESALQ,
            "ano_atual": meta_atual,
            "variaveis_ano_atual": ag.variaveis_com_dados(df_atual),
        })
    else:
        resposta["ano_atual"] = None
        if not info["tem_registros"]:
            resposta["aviso"] = ("Os dados horários desta estação ainda não foram processados pela atualização "
                                 "automática; por enquanto o site mostra os totais diários.")
    resposta["limites"] = postos.limites(info["id"])
    return _resposta(resposta, cache=not atualizar)


@app.get("/api/posto/{pid}/painel")
def posto_painel(pid: str, inicio: str | None = None, fim: str | None = None, passo: str = "auto"):
    ini, fi = _periodo_posto(pid, inicio, fim)
    df15, diario, metas, info = _carregar(pid, ini, fi)
    resolucao = ag.resolucao_min(df15) if not df15.empty else (1440 if not diario.empty else info["resolucao_min"])
    if passo == "auto":
        passo = ag.escolher_passo(ini, fi, resolucao)
    if passo not in ag.PASSOS:
        raise HTTPException(400, "passo inválido")
    passo = ag.ajustar_passo(passo, resolucao)
    if df15.empty and diario.empty:
        s = None
    else:
        s = ag.serie(df15, diario, passo)
    return _resposta({
        "posto": {k: info[k] for k in ("id", "nome", "nome_curto", "codigo", "fonte", "resolucao_min")},
        "resumo": ag.resumo(df15, diario, ini, fi),
        "passo": passo,
        "serie": ag.serie_para_json(s) if s is not None else {"t": []},
        "origem": metas,
    })


@app.get("/api/posto/{pid}/dados")
def posto_dados(
    pid: str, inicio: str | None = None, fim: str | None = None,
    pagina: int = Query(1, ge=1), por_pagina: int = Query(100, ge=10, le=1000),
    so_chuva: bool = False, ordem: str = "desc",
):
    ini, fi = _periodo_posto(pid, inicio, fim, 7)
    _posto(pid)
    df15, _ = postos.carregar_registros(pid, ini, fi)
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
        "resolucao_min": ag.resolucao_min(df15),
        "linhas": ag.tabela_para_json(pagina_df),
    })


def _coluna_intensidade(tab: pd.DataFrame) -> str:
    """Primeira intensidade disponível (estações horárias não têm I15 nem I30)."""
    return next((c for c in ("i15_mm_h", "i30_mm_h", "i60_mm_h") if tab[c].notna().any()), "intensidade_media_mm_h")


@app.get("/api/posto/{pid}/eventos")
def posto_eventos(
    pid: str, inicio: str | None = None, fim: str | None = None,
    intervalo_seco_h: float = Query(6.0, gt=0, le=72), chuva_min_mm: float = Query(1.0, ge=0),
):
    ini, fi = _periodo_posto(pid, inicio, fim, 90)
    _posto(pid)
    df15, _ = postos.carregar_registros(pid, ini, fi)
    tab = ev.eventos_chuva(df15, intervalo_seco_h, chuva_min_mm)
    resumo = {"n_eventos": int(len(tab)), "resolucao_min": ag.resolucao_min(df15)}
    if len(tab):
        col = _coluna_intensidade(tab)
        maior = tab.loc[tab["chuva_mm"].idxmax()]
        intenso = tab.loc[tab[col].idxmax()]
        resumo.update({
            "chuva_total_eventos_mm": round(float(tab["chuva_mm"].sum()), 2),
            "duracao_media_min": round(float(tab["duracao_min"].mean())),
            "maior_evento": {"evento": int(maior["evento"]), "chuva_mm": float(maior["chuva_mm"]),
                             "inicio": maior["inicio"]},
            "mais_intenso": {"evento": int(intenso["evento"]), "coluna": col, "intensidade_mm_h": float(intenso[col]),
                             "i15_mm_h": None if pd.isna(intenso["i15_mm_h"]) else float(intenso["i15_mm_h"]),
                             "inicio": intenso["inicio"]},
        })
    return _resposta({
        "parametros": {"inicio": ini, "fim": fi, "intervalo_seco_h": intervalo_seco_h, "chuva_min_mm": chuva_min_mm},
        "resumo": resumo,
        "eventos": ag.tabela_para_json(tab),
    })


@app.get("/api/posto/{pid}/relatorio")
def posto_relatorio(pid: str, inicio: str | None = None, fim: str | None = None, escala: str = "mensal"):
    ini, fi = _periodo_posto(pid, inicio, fim, 365)
    if escala == "diario" and (fi - ini).days > 366 * 20:
        raise HTTPException(400, "O relatório diário aceita até 20 anos; use o semanal, mensal ou anual")
    df15, diario, metas, _ = _carregar(pid, ini, fi)
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


@app.get("/api/posto/{pid}/maximas")
def posto_maximas(pid: str, inicio: str | None = None, fim: str | None = None):
    ini, fi = _periodo_posto(pid, inicio, fim, 365 * 30)
    _posto(pid)
    df15, _ = postos.carregar_registros(pid, ini, fi)
    return _resposta(ev.maximas_anuais(df15))


@app.get("/api/posto/{pid}/download")
def posto_download(
    pid: str, tipo: str = "dados", formato: str = "csv_r",
    inicio: str | None = None, fim: str | None = None, so_chuva: bool = False,
    intervalo_seco_h: float = 6.0, chuva_min_mm: float = 1.0,
):
    ini, fi = _periodo_posto(pid, inicio, fim, 30)
    df15, diario, _, info = _carregar(pid, ini, fi)
    base = f"{_nome_arquivo(info)}_{tipo}_{ini:%Y%m%d}_{fi:%Y%m%d}"
    if tipo == "dados":
        if so_chuva:
            df15 = df15[df15["chuva_mm"] > 0]
        tab = df15[_so_com_dados(df15, COLUNAS_TABELA_15MIN)]
        aba = "Dados 15 min" if info["resolucao_min"] == 15 else "Dados horários"
    elif tipo in ("diario", "semanal", "mensal", "anual"):
        tab = _sem_vazias(ag.relatorio(diario, df15, tipo))
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
    return _exportar(tab, formato, base, aba, _leia_me_base(info, aba, ini, fi))


@app.get("/api/posto/{pid}/planilha")
def posto_planilha(pid: str, inicio: str | None = None, fim: str | None = None,
                   intervalo_seco_h: float = 6.0, chuva_min_mm: float = 1.0, cad: float = 100.0):
    """Planilha hidrológica completa (.xlsx com várias abas)."""
    ini, fi = _periodo_posto(pid, inicio, fim, 365)
    df15, diario, _, info = _carregar(pid, ini, fi)
    if df15.empty and diario.empty:
        raise HTTPException(404, "Sem dados no período")

    abas = [
        ("Diário", _sem_vazias(ag.relatorio(diario, df15, "diario"))),
        ("Semanal", _sem_vazias(ag.relatorio(diario, df15, "semanal"))),
        ("Mensal", _sem_vazias(ag.relatorio(diario, df15, "mensal"))),
        ("Anual", _sem_vazias(ag.relatorio(diario, df15, "anual"))),
    ]
    extra = []
    if not df15.empty:
        abas += [
            ("Eventos de chuva", ev.eventos_chuva(df15, intervalo_seco_h, chuva_min_mm)),
            ("Máximas anuais", ev.maximas_para_tabela(ev.maximas_anuais(df15))),
        ]
        extra += [
            ("Eventos de chuva", f"Separados por ≥ {intervalo_seco_h:g} h sem chuva; só eventos com ≥ {chuva_min_mm:g} mm. "
                                 "Intensidade média = chuva total ÷ duração; I15/I30/I60 = maiores intensidades "
                                 "em janelas móveis de 15, 30 e 60 min (em estações horárias, só I60)."),
            ("Máximas anuais", "Maior chuva de cada ano em janelas móveis (base para curvas IDF). "
                               "Anos com cobertura < 80% devem ser usados com cuidado."),
        ]
    # Balanço hídrico mensal, se houver temperatura
    if diario["temp_c"].notna().sum() > 300:
        try:
            todo = postos.carregar_diario(info["id"])
            ini_p, fim_p = pd.Period(ini, "M"), pd.Period(fi, "M")
            bh = calcular_balanco(todo, float(info["lat"]), ini_p, fim_p, cad, "mensal")
            abas.append(("Balanço hídrico", bh["sequencial"]))
            abas.append(("BH normal", pd.DataFrame(bh["normal"])))
            extra.append(("Balanço hídrico", f"Thornthwaite & Mather (1955), ETP de Thornthwaite (1948), CAD = {cad:g} mm."))
        except ValueError as exc:
            extra.append(("Balanço hídrico", f"Não calculado: {exc}"))
    else:
        extra.append(("Balanço hídrico", "Não calculado: o período não tem dados de temperatura suficientes."))

    nome_registros = "Dados 15 min" if info["resolucao_min"] == 15 else "Dados horários"
    if df15.empty:
        pass
    elif len(df15) <= 70_000:
        abas.insert(0, (nome_registros, df15[_so_com_dados(df15, COLUNAS_TABELA_15MIN)]))
    else:
        extra.append((nome_registros, "Período longo demais para a planilha: baixe os registros em CSV."))

    conteudo = ex.xlsx([(n, ex.limpar_para_planilha(t)) for n, t in abas],
                       _leia_me_base(info, "Planilha hidrológica", ini, fi, extra))
    return _arquivo(conteudo, f"planilha_hidrologica_{_nome_arquivo(info)}_{ini:%Y%m%d}_{fi:%Y%m%d}.xlsx",
                    FORMATOS["xlsx"][0])


# Rotas antigas da ESALQ (mesmo resultado de /api/posto/esalq/...)
@app.get("/api/esalq/meta")
def esalq_meta(atualizar: bool = False):
    return posto_meta("esalq", atualizar)


@app.get("/api/esalq/painel")
def esalq_painel(inicio: str | None = None, fim: str | None = None, passo: str = "auto"):
    return posto_painel("esalq", inicio, fim, passo)


@app.get("/api/esalq/dados")
def esalq_dados(inicio: str | None = None, fim: str | None = None,
                pagina: int = Query(1, ge=1), por_pagina: int = Query(100, ge=10, le=1000),
                so_chuva: bool = False, ordem: str = "desc"):
    return posto_dados("esalq", inicio, fim, pagina, por_pagina, so_chuva, ordem)


@app.get("/api/esalq/eventos")
def esalq_eventos(inicio: str | None = None, fim: str | None = None,
                  intervalo_seco_h: float = Query(6.0, gt=0, le=72), chuva_min_mm: float = Query(1.0, ge=0)):
    return posto_eventos("esalq", inicio, fim, intervalo_seco_h, chuva_min_mm)


@app.get("/api/esalq/relatorio")
def esalq_relatorio(inicio: str | None = None, fim: str | None = None, escala: str = "mensal"):
    return posto_relatorio("esalq", inicio, fim, escala)


@app.get("/api/esalq/maximas")
def esalq_maximas(inicio: str | None = None, fim: str | None = None):
    return posto_maximas("esalq", inicio, fim)


@app.get("/api/esalq/download")
def esalq_download(tipo: str = "dados", formato: str = "csv_r", inicio: str | None = None, fim: str | None = None,
                   so_chuva: bool = False, intervalo_seco_h: float = 6.0, chuva_min_mm: float = 1.0):
    return posto_download("esalq", tipo, formato, inicio, fim, so_chuva, intervalo_seco_h, chuva_min_mm)


@app.get("/api/esalq/planilha")
def esalq_planilha(inicio: str | None = None, fim: str | None = None,
                   intervalo_seco_h: float = 6.0, chuva_min_mm: float = 1.0, cad: float = 100.0):
    return posto_planilha("esalq", inicio, fim, intervalo_seco_h, chuva_min_mm, cad)


# ---------------------------------------------------------------------------
# Postos e balanço hídrico
# ---------------------------------------------------------------------------


@app.get("/api/postos")
def listar_postos(busca: str = ""):
    lista = postos.listar(busca)
    fins = [p["fim_dados"] for p in lista if p["fonte"] == "inmet" and p["fim_dados"]]
    return _resposta({
        "postos": lista,
        "referencia": {
            # Último dia publicado pelo INMET (o mais comum entre as estações) e o da ESALQ
            "ultimo_dia_inmet": max(set(fins), key=fins.count) if fins else None,
            "ultimo_dia_esalq": next((p["fim_dados"] for p in lista if p["fonte"] == "esalq"), None),
        },
    })


def _resumo_diario_mapa(d: pd.DataFrame, dias: int) -> dict:
    """Totais de um posto no período (a partir da série diária)."""
    chuva = d["chuva_mm"]
    validos = int(chuva.count())
    com_chuva = d.loc[chuva.notna(), "dia"]
    maior = d.loc[chuva.idxmax()] if validos else None
    return {
        "chuva_mm": round(float(chuva.sum()), 1) if validos else None,
        "dias_com_dados": validos,
        "cobertura_pct": round(100 * validos / dias, 1),
        "dias_chuva": int((chuva >= 1).sum()),
        "chuva_max_dia_mm": round(float(maior["chuva_mm"]), 1) if maior is not None else None,
        "data_chuva_max_dia": maior["dia"] if maior is not None else None,
        "temp_media_c": round(float(d["temp_c"].mean()), 1) if d["temp_c"].notna().any() else None,
        "ultimo_dia": com_chuva.max() if validos else None,
    }


@app.get("/api/mapa")
def mapa(inicio: str = Query(..., description="AAAA-MM-DD"), fim: str = Query(..., description="AAAA-MM-DD")):
    """Chuva de cada posto no período (para colorir o mapa)."""
    ini, fi = _data(inicio, "inicio"), _data(fim, "fim")
    if ini > fi:
        ini, fi = fi, ini
    if (fi - ini).days > 366 * 60:
        raise HTTPException(400, "Período muito longo (máximo 60 anos)")
    dias = (fi - ini).days + 1
    lista = postos.listar()
    d_inmet = inmet.diario_todas(ini, fi)
    grupos = {cod: g for cod, g in d_inmet.groupby("codigo")} if not d_inmet.empty else {}
    vazio = pd.DataFrame({"dia": pd.Series(dtype="datetime64[ns]"), "chuva_mm": pd.Series(dtype=float),
                          "temp_c": pd.Series(dtype=float)})
    saida = []
    for p in lista:
        if p["fonte"] == "esalq":
            d = postos.carregar_diario("esalq", ini, fi)
            # dias com menos de 80% dos registros não entram no total
            d = d.assign(chuva_mm=d["chuva_mm"].where(d["cobertura_pct"] >= 80))
        else:
            d = grupos.get(p["codigo"], vazio)
        campos = {k: p[k] for k in ("id", "fonte", "codigo", "nome", "nome_curto", "municipio", "lat", "lon", "alt",
                                    "rede", "resolucao_min", "inicio_dados", "fim_dados", "tem_dados", "tem_registros")}
        saida.append({**campos, **_resumo_diario_mapa(d, dias)})
    return _resposta({"periodo": {"inicio": ini, "fim": fi, "dias": dias}, "postos": saida})


def _distancia_km(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _matriz_correlacao(series: dict[str, pd.Series], ids: list[str], minimo: int) -> dict:
    """Correlação de Pearson entre cada par de postos, só nos períodos em que ambos têm dado."""
    r = [[None] * len(ids) for _ in ids]
    n = [[0] * len(ids) for _ in ids]
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if j < i or a not in series or b not in series:
                continue
            par = pd.concat([series[a], series[b]], axis=1, join="inner").dropna()
            n[i][j] = n[j][i] = int(len(par))
            if len(par) >= minimo and par.iloc[:, 0].std() > 0 and par.iloc[:, 1].std() > 0:
                v = 1.0 if i == j else round(float(par.iloc[:, 0].corr(par.iloc[:, 1])), 3)
                r[i][j] = r[j][i] = v
    return {"ids": ids, "r": r, "n": n, "minimo": minimo}


COLUNAS_COMPARAR = ["periodo", "inicio", "p_mm", "t_c", "etp_mm", "etr_mm", "def_mm", "exc_mm", "arm_mm",
                    "cobertura_p_pct", "cobertura_t_pct"]

VARIAVEIS_CORRELACAO = {
    "chuva_diaria": ("Chuva diária", "mm", 30),
    "chuva_mensal": ("Chuva mensal", "mm", 6),
    "temp_mensal": ("Temperatura média mensal", "°C", 6),
}


def _series_para_correlacao(diario: pd.DataFrame, ini: date, fim: date) -> dict[str, pd.Series]:
    """Séries observadas (sem preenchimento) para correlacionar postos.

    Dia vale se o posto tem o dia completo (ESALQ: ≥ 80% dos registros; INMET: ≥ 18 h).
    Mês vale se ≥ 90% dos dias têm dado.
    """
    d = diario[(diario["dia"] >= pd.Timestamp(ini)) & (diario["dia"] <= pd.Timestamp(fim))]
    if d.empty:
        vazio = pd.Series(dtype=float)
        return {k: vazio for k in VARIAVEIS_CORRELACAO}
    if "cobertura_pct" in d:
        d = d.assign(chuva_mm=d["chuva_mm"].where(d["cobertura_pct"].isna() | (d["cobertura_pct"] >= 80)))
    d = d.set_index("dia")
    meses = d.index.to_period("M")
    dias_mes = pd.Series(d.index.days_in_month, index=d.index).groupby(meses).first()
    p, t = d["chuva_mm"], d["temp_c"]
    p_m = p.groupby(meses).sum(min_count=1).where(p.groupby(meses).count() >= 0.9 * dias_mes)
    t_m = t.groupby(meses).mean().where(t.groupby(meses).count() >= 0.9 * dias_mes)
    return {"chuva_diaria": p.dropna(), "chuva_mensal": p_m.dropna(), "temp_mensal": t_m.dropna()}


def _meses(inicio: str, fim: str) -> tuple[pd.Period, pd.Period]:
    try:
        ini_p, fim_p = pd.Period(inicio, "M"), pd.Period(fim, "M")
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Use inicio e fim no formato AAAA-MM") from exc
    if fim_p < ini_p:
        ini_p, fim_p = fim_p, ini_p
    if (fim_p - ini_p).n > 12 * 60:
        raise HTTPException(400, "Período muito longo (máximo 60 anos)")
    return ini_p, fim_p


@app.get("/api/comparar")
def comparar(
    lista: str = Query(..., alias="postos", description="ids separados por vírgula (2 a 6)"),
    inicio: str = Query(..., description="AAAA-MM"), fim: str = Query(..., description="AAAA-MM"),
    cad: float = 100.0,
):
    """Balanço hídrico de vários postos no mesmo período + correlação entre eles."""
    ids = list(dict.fromkeys(postos.normalizar_id(x) for x in lista.split(",") if x.strip()))
    if not 2 <= len(ids) <= 6:
        raise HTTPException(400, "Escolha de 2 a 6 postos para comparar")
    ini_p, fim_p = _meses(inicio, fim)
    if not 1 <= cad <= 1000:
        raise HTTPException(400, "CAD deve estar entre 1 e 1000 mm")
    ini_d, fim_d = ini_p.start_time.date(), fim_p.end_time.date()

    infos = [_posto(pid) for pid in ids]
    resultados = []
    series: dict[str, dict[str, pd.Series]] = {k: {} for k in VARIAVEIS_CORRELACAO}
    for info in infos:
        pid = info["id"]
        campos = {k: info[k] for k in ("id", "fonte", "codigo", "nome", "nome_curto", "municipio", "lat", "lon", "alt",
                                       "rede", "inicio_dados", "fim_dados")}
        try:
            diario = postos.carregar_diario(pid)
            if diario.empty:
                raise ValueError("Ainda não há dados diários deste posto no site")
            res = calcular_balanco(diario, float(info["lat"]), ini_p, fim_p, cad, "mensal")
        except ValueError as exc:
            resultados.append({"posto": campos, "erro": str(exc)})
            continue
        seq = res["sequencial"]
        resultados.append({
            "posto": campos,
            "totais": res["totais"],
            "totais_normal": res["totais_normal"],
            "indices": res["indices"],
            "base_normais": res["base_normais"],
            "avisos": res["avisos"],
            "cobertura_p_pct": round(float(seq["cobertura_p_pct"].mean()), 1),
            "cobertura_t_pct": round(float(seq["cobertura_t_pct"].mean()), 1),
            "mensal": ag.tabela_para_json(seq[[c for c in COLUNAS_COMPARAR if c in seq]]),
        })
        for chave, serie in _series_para_correlacao(diario, ini_d, fim_d).items():
            series[chave][pid] = serie

    ids_ok = [r["posto"]["id"] for r in resultados if "erro" not in r]
    distancias = [[round(_distancia_km(a, b), 1) for b in infos] for a in infos]
    return _resposta({
        "parametros": {"inicio": str(ini_p), "fim": str(fim_p), "cad_mm": cad, "meses": (fim_p - ini_p).n + 1,
                       "metodo": "Thornthwaite (1948) + Thornthwaite & Mather (1955)"},
        "postos": resultados,
        "distancias_km": {"ids": ids, "km": distancias},
        "correlacao": {k: _matriz_correlacao(series[k], ids_ok, v[2]) for k, v in VARIAVEIS_CORRELACAO.items()},
    })


@app.get("/api/comparar/par")
def comparar_par(
    a: str, b: str,
    inicio: str = Query(..., description="AAAA-MM"), fim: str = Query(..., description="AAAA-MM"),
    variavel: str = "chuva_diaria",
):
    """Valores dos dois postos nos mesmos dias (ou meses), correlação e reta de regressão (b em função de a)."""
    if variavel not in VARIAVEIS_CORRELACAO:
        raise HTTPException(400, "variavel deve ser chuva_diaria, chuva_mensal ou temp_mensal")
    ini_p, fim_p = _meses(inicio, fim)
    ini_d, fim_d = ini_p.start_time.date(), fim_p.end_time.date()
    ia, ib = _posto(a), _posto(b)
    sa = _series_para_correlacao(postos.carregar_diario(ia["id"]), ini_d, fim_d)[variavel]
    sb = _series_para_correlacao(postos.carregar_diario(ib["id"]), ini_d, fim_d)[variavel]
    par = pd.concat([sa.rename("x"), sb.rename("y")], axis=1, join="inner").dropna()
    nome, unidade, minimo = VARIAVEIS_CORRELACAO[variavel]
    resposta = {
        "variavel": variavel, "rotulo": nome, "unidade": unidade,
        "a": {k: ia[k] for k in ("id", "nome", "nome_curto", "codigo", "fonte")},
        "b": {k: ib[k] for k in ("id", "nome", "nome_curto", "codigo", "fonte")},
        "distancia_km": round(_distancia_km(ia, ib), 1),
        "n": int(len(par)), "minimo": minimo, "r": None, "regressao": None,
        "t": [str(i) if isinstance(i, pd.Period) else i for i in par.index],
        "x": par["x"].round(2).tolist(), "y": par["y"].round(2).tolist(),
    }
    if len(par) >= minimo and par["x"].std() > 0 and par["y"].std() > 0:
        r = float(par["x"].corr(par["y"]))
        inclinacao, intercepto = np.polyfit(par["x"], par["y"], 1)
        resposta["r"] = round(r, 3)
        resposta["regressao"] = {"inclinacao": round(float(inclinacao), 4), "intercepto": round(float(intercepto), 3),
                                 "r2": round(r * r, 3)}
    return _resposta(resposta)


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
