"""Exportação: CSV para R/Python, CSV para Excel (pt-BR) e planilhas XLSX."""

from __future__ import annotations

import io
from datetime import datetime

import numpy as np
import pandas as pd

from .config import FUSO_BR

# coluna -> (rótulo em português, casas decimais)
ROTULOS = {
    "data_hora": ("Data/hora", None),
    "dia": ("Data", None),
    "periodo": ("Período", None),
    "inicio": ("Início", None),
    "fim": ("Fim", None),
    "evento": ("Evento", 0),
    "chuva_mm": ("Chuva (mm)", 2),
    "intensidade_mm_h": ("Intensidade (mm/h)", 2),
    "intensidade_max_mm_h": ("Intensidade máx. 15 min (mm/h)", 2),
    "momento_intensidade_max": ("Momento da intensidade máx.", None),
    "chuva_acum_dia_mm": ("Chuva acumulada no dia (mm)", 2),
    "intervalo_h": ("Intervalo (h)", 3),
    "temp_c": ("Temperatura média (°C)", 1),
    "temp_max_c": ("Temperatura máx. (°C)", 1),
    "temp_min_c": ("Temperatura mín. (°C)", 1),
    "temp_max_media_c": ("Média das máximas (°C)", 1),
    "temp_min_media_c": ("Média das mínimas (°C)", 1),
    "ur_pct": ("Umidade relativa (%)", 1),
    "vento_ms": ("Velocidade do vento (m/s)", 2),
    "vento_max_ms": ("Rajada máx. (m/s)", 2),
    "vento_dir_graus": ("Direção do vento (°)", 0),
    "rad_w_m2": ("Radiação global (W/m²)", 1),
    "rad_mj_m2": ("Radiação global (MJ/m²/dia)", 2),
    "pressao_hpa": ("Pressão (hPa)", 1),
    "registros": ("Registros", 0),
    "cobertura_pct": ("Cobertura de dados (%)", 1),
    "dias_chuva": ("Dias com chuva ≥ 1 mm", 0),
    "chuva_max_diaria_mm": ("Chuva máx. diária (mm)", 2),
    "data_chuva_max_diaria": ("Dia da chuva máx.", None),
    "dias_com_dados": ("Dias com dados", 0),
    "duracao_min": ("Duração (min)", 0),
    "intensidade_media_mm_h": ("Intensidade média (mm/h)", 2),
    "i15_mm_h": ("I15 máx. (mm/h)", 2),
    "i30_mm_h": ("I30 máx. (mm/h)", 2),
    "i60_mm_h": ("I60 máx. (mm/h)", 2),
    "momento_pico": ("Momento do pico", None),
    "registros_falhos": ("Registros com falha", 0),
    "ano": ("Ano", 0),
    "chuva_total_mm": ("Chuva total (mm)", 1),
    "chuva_max_dia_mm": ("Chuva máx. em 1 dia (mm)", 2),
    "data_chuva_max_dia": ("Dia da chuva máx.", None),
    # Balanço hídrico
    "mes": ("Mês", 0),
    "t_c": ("T (°C)", 1),
    "p_mm": ("P (mm)", 1),
    "etp_mm": ("ETP (mm)", 1),
    "p_etp_mm": ("P − ETP (mm)", 1),
    "neg_ac_mm": ("NEG.AC (mm)", 1),
    "arm_mm": ("ARM (mm)", 1),
    "alt_mm": ("ALT (mm)", 1),
    "etr_mm": ("ETR (mm)", 1),
    "def_mm": ("DEF (mm)", 1),
    "exc_mm": ("EXC (mm)", 1),
    "cobertura_p_pct": ("Dados de chuva (%)", 0),
    "cobertura_t_pct": ("Dados de temperatura (%)", 0),
    "p_estimada": ("P estimada", None),
    "t_estimada": ("T estimada", None),
    "codigo": ("Código", None),
    "horas": ("Horas com dados", 0),
}


def _rotulo(col: str) -> str:
    if col in ROTULOS:
        return ROTULOS[col][0]
    if col.startswith("p_") and col.endswith("min_mm"):
        return f"P máx. {col[2:-6]} min (mm)"
    if col.startswith("i_") and col.endswith("min_mm_h"):
        return f"I máx. {col[2:-8]} min (mm/h)"
    return col


def _casas(col: str) -> int | None:
    if col in ROTULOS:
        return ROTULOS[col][1]
    if col.startswith(("p_", "i_")):
        return 2
    return None


def _eh_data_pura(s: pd.Series) -> bool:
    v = s.dropna()
    return not v.empty and bool((v.dt.normalize() == v).all())


def _datas_como_texto(df: pd.DataFrame, fmt_data: str, fmt_hora: str) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            fmt = fmt_data if _eh_data_pura(df[c]) else fmt_hora
            df[c] = df[c].dt.strftime(fmt)
    return df


def csv_r(df: pd.DataFrame) -> bytes:
    """CSV "tidy": vírgula como separador, ponto decimal, datas ISO, NA nas falhas, UTF-8 sem BOM.

    No R:  dados <- read.csv("arquivo.csv")   ou   readr::read_csv("arquivo.csv")
    """
    df = _datas_como_texto(df, "%Y-%m-%d", "%Y-%m-%d %H:%M:%S")
    for c in df.columns:
        if df[c].dtype == bool:
            df[c] = df[c].map({True: "TRUE", False: "FALSE"})
    return df.to_csv(index=False, sep=",", decimal=".", na_rep="NA", float_format="%.6g").encode("utf-8")


def csv_excel(df: pd.DataFrame) -> bytes:
    """CSV para Excel em português: ponto e vírgula, vírgula decimal, datas dd/mm/aaaa."""
    df = _datas_como_texto(df, "%d/%m/%Y", "%d/%m/%Y %H:%M")
    for c in df.columns:
        casas = _casas(c)
        if pd.api.types.is_float_dtype(df[c]):
            fmt = f"{{:.{casas}f}}" if casas is not None else "{:.4g}"
            df[c] = df[c].map(lambda x, f=fmt: "" if pd.isna(x) else f.format(x).replace(".", ","))
        elif df[c].dtype == bool:
            df[c] = df[c].map({True: "sim", False: "não"})
    df = df.rename(columns={c: _rotulo(c) for c in df.columns})
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def xlsx(planilhas: list[tuple[str, pd.DataFrame]], leia_me: list[tuple[str, str]] | None = None) -> bytes:
    """Gera um .xlsx com uma aba por tabela (cabeçalho formatado, filtros, colunas ajustadas)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(
        buf, engine="xlsxwriter",
        datetime_format="dd/mm/yyyy hh:mm", date_format="dd/mm/yyyy",
        engine_kwargs={"options": {"strings_to_numbers": False, "nan_inf_to_errors": True}},
    ) as escritor:
        livro = escritor.book
        f_cab = livro.add_format({"bold": True, "bg_color": "#0F3D3E", "font_color": "#FFFFFF",
                                  "text_wrap": True, "valign": "vcenter", "border": 1})
        f_titulo = livro.add_format({"bold": True, "font_size": 14, "font_color": "#0F3D3E"})
        f_chave = livro.add_format({"bold": True, "valign": "top"})
        f_texto = livro.add_format({"text_wrap": True, "valign": "top"})
        formatos_num = {n: livro.add_format({"num_format": "0" if n == 0 else "0." + "0" * n}) for n in range(0, 5)}
        f_data = livro.add_format({"num_format": "dd/mm/yyyy"})
        f_data_hora = livro.add_format({"num_format": "dd/mm/yyyy hh:mm"})

        if leia_me:
            ws = livro.add_worksheet("Leia-me")
            ws.write(0, 0, "Análise de dados meteorológicos – ESALQ / postos de SP", f_titulo)
            for i, (k, v) in enumerate(leia_me, start=2):
                ws.write(i, 0, k, f_chave)
                ws.write(i, 1, v, f_texto)
            ws.set_column(0, 0, 28)
            ws.set_column(1, 1, 100)

        for nome, df in planilhas:
            nome = nome[:31]
            df = df.copy()
            for c in df.columns:
                if isinstance(df[c].dtype, pd.DatetimeTZDtype):
                    df[c] = df[c].dt.tz_localize(None)
                if df[c].dtype == bool:
                    df[c] = df[c].map({True: "sim", False: "não"})
            df.columns = [_rotulo(c) for c in df.columns]
            df.to_excel(escritor, sheet_name=nome, index=False)
            ws = escritor.sheets[nome]
            for j, col in enumerate(df.columns):
                ws.write(0, j, col, f_cab)
                original = list(ROTULOS.keys())
                serie = df[col]
                largura = max(10, min(40, len(str(col)) + 2))
                fmt = None
                if pd.api.types.is_datetime64_any_dtype(serie):
                    fmt = f_data if _eh_data_pura(serie) else f_data_hora
                    largura = max(largura, 12 if fmt is f_data else 16)
                elif pd.api.types.is_float_dtype(serie):
                    chave = next((k for k in original if ROTULOS[k][0] == col), None)
                    casas = ROTULOS[chave][1] if chave else 2
                    fmt = formatos_num.get(casas if casas is not None else 2)
                ws.set_column(j, j, largura, fmt)
            ws.set_row(0, 32)
            ws.freeze_panes(1, 0)
            if len(df):
                ws.autofilter(0, 0, len(df), len(df.columns) - 1)
    return buf.getvalue()


def gerado_em() -> str:
    return datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M")


def limpar_para_planilha(df: pd.DataFrame) -> pd.DataFrame:
    """Troca ±inf por NaN e garante tipos simples."""
    return df.replace([np.inf, -np.inf], np.nan)
