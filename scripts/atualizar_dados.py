"""Atualiza os dados guardados no repositório.

    python scripts/atualizar_dados.py esalq            # anos novos/incompletos da ESALQ
    python scripts/atualizar_dados.py esalq --desde 1997 --forcar
    python scripts/atualizar_dados.py inmet            # pacotes anuais do INMET (estações de SP)
    python scripts/atualizar_dados.py inmet --anos 2024 2025
    python scripts/atualizar_dados.py tudo

Roda toda semana no GitHub Actions (.github/workflows/atualizar-dados.yml),
que faz o commit dos arquivos novos; a Vercel publica a nova versão sozinha.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hidro import inmet  # noqa: E402
from hidro.config import (  # noqa: E402
    ANO_INICIAL_BUSCA_ESALQ, ANO_INICIAL_INMET, COLUNAS_15MIN, DIR_DADOS, DIR_ESALQ, DIR_INMET_DIARIO,
    FUSO_BR, URL_INMET_ANUAL, URLS_ESALQ,
)
from hidro.esalq import ler_arquivo_esalq  # noqa: E402

ARQ_ATUALIZACAO = DIR_DADOS / "atualizacao.json"
CABECALHO = {"User-Agent": "Mozilla/5.0 (analise-chuva-esalq; atualizacao de dados)"}
GZIP = {"method": "gzip", "compresslevel": 9, "mtime": 0}


def agora() -> str:
    return datetime.now(FUSO_BR).isoformat(timespec="seconds")


def ler_json(caminho: Path, padrao):
    if caminho.exists():
        try:
            return json.loads(caminho.read_text("utf-8"))
        except ValueError:
            pass
    return padrao


def gravar_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")


def baixar(url: str, tentativas: int = 3, timeout: int = 90, destino: Path | None = None) -> bytes | None:
    """Baixa com novas tentativas. Retorna None se o arquivo não existir (404)."""
    for t in range(1, tentativas + 1):
        try:
            with requests.get(url, headers=CABECALHO, timeout=timeout, stream=True) as r:
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                if destino is not None:
                    with open(destino, "wb") as f:
                        for bloco in r.iter_content(1 << 20):
                            f.write(bloco)
                    return b""
                return r.content
        except requests.RequestException as exc:
            print(f"  tentativa {t}/{tentativas} falhou: {exc}")
            time.sleep(5 * t)
    raise RuntimeError(f"Falha ao baixar {url}")


# ---------------------------------------------------------------------------
# ESALQ
# ---------------------------------------------------------------------------


def _ano_completo(caminho: Path) -> bool:
    """True se o arquivo já tem as variáveis além da chuva."""
    if not caminho.exists():
        return False
    df = pd.read_csv(caminho, nrows=3000)
    extras = [c for c in COLUNAS_15MIN[2:] if c in df]
    return bool(extras) and df[extras].notna().any().any()


def _gravar_ano_esalq(ano: int, novo: pd.DataFrame, prioridade_novo: bool) -> int:
    destino = DIR_ESALQ / f"esalq_{ano}.csv.gz"
    if destino.exists():
        antigo = pd.read_csv(destino, parse_dates=["data_hora"])
        if prioridade_novo:
            df = pd.concat([antigo, novo], ignore_index=True).drop_duplicates("data_hora", keep="last")
        else:
            df = pd.concat([antigo, novo[~novo["data_hora"].isin(antigo["data_hora"])]], ignore_index=True)
    else:
        df = novo
    for c in COLUNAS_15MIN:
        if c not in df:
            df[c] = float("nan")
    df = df[COLUNAS_15MIN].sort_values("data_hora")
    df.to_csv(destino, index=False, float_format="%.5g", date_format="%Y-%m-%d %H:%M:%S", compression=GZIP)
    return len(df)


def atualizar_esalq(anos: list[int] | None, desde: int, forcar: bool) -> None:
    DIR_ESALQ.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now(FUSO_BR).date()
    anos = anos or list(range(desde, hoje.year + 1))
    colunas = ler_json(DIR_ESALQ / "colunas.json", {})
    registro = ler_json(DIR_ESALQ / "anos.json", {"disponiveis": [], "inexistentes": []})
    disponiveis = set(registro.get("disponiveis", []))
    inexistentes = set(registro.get("inexistentes", []))

    for ano in anos:
        caminho = DIR_ESALQ / f"esalq_{ano}.csv.gz"
        recente = ano >= hoje.year - 1
        if not forcar and not recente and _ano_completo(caminho):
            print(f"ESALQ {ano}: já completo")
            disponiveis.add(ano)
            continue
        if not forcar and ano in inexistentes and ano < hoje.year:
            print(f"ESALQ {ano}: não existe no site (pulando)")
            continue
        # Endereço novo primeiro; o antigo só é tentado se o novo não responder
        conteudo, nao_existe, erros = None, False, []
        for i, modelo in enumerate(URLS_ESALQ):
            url = modelo.format(ano=ano)
            print(f"ESALQ {ano}: baixando {url}")
            try:
                conteudo = baixar(url)
            except RuntimeError as exc:
                erros.append(str(exc))
                continue
            nao_existe = conteudo is None and i == 0
            break
        if conteudo is None:
            if nao_existe:
                print("  não encontrado (404)")
                inexistentes.add(ano)
            else:
                print(f"  ERRO: {'; '.join(erros) or 'arquivo não encontrado'}")
            continue
        try:
            df, info = ler_arquivo_esalq(conteudo)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERRO ao ler o arquivo: {exc}")
            if len(conteudo) < 2048:  # página de erro em vez de planilha
                inexistentes.add(ano)
            continue

        # Cada registro vai para o arquivo do ano do seu timestamp
        for ano_ts, parte in df.groupby(df["data_hora"].dt.year):
            n = _gravar_ano_esalq(int(ano_ts), parte, prioridade_novo=(int(ano_ts) == ano))
            disponiveis.add(int(ano_ts))
            print(f"  {ano_ts}: {len(parte)} registros (arquivo com {n})")
        info["baixado_em"] = agora()
        colunas[str(ano)] = info
        inexistentes.discard(ano)
        print(f"  variáveis encontradas: {', '.join(info['mapeamento']) or 'nenhuma'}")

    gravar_json(DIR_ESALQ / "colunas.json", colunas)
    gravar_json(DIR_ESALQ / "anos.json", {
        "disponiveis": sorted(disponiveis), "inexistentes": sorted(inexistentes), "verificado_em": agora(),
    })
    marcar_atualizacao("esalq")


# ---------------------------------------------------------------------------
# INMET
# ---------------------------------------------------------------------------


def atualizar_inmet(anos: list[int] | None, forcar: bool) -> None:
    DIR_INMET_DIARIO.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now(FUSO_BR).date()
    anos = anos or list(range(ANO_INICIAL_INMET, hoje.year + 1))
    catalogo = {e["codigo"]: e for e in inmet.estacoes()}

    for ano in anos:
        destino = DIR_INMET_DIARIO / f"inmet_sp_{ano}.csv.gz"
        recente = ano >= hoje.year - (1 if hoje.month <= 2 else 0)
        if destino.exists() and not forcar and not recente:
            print(f"INMET {ano}: já existe")
            continue
        url = URL_INMET_ANUAL.format(ano=ano)
        print(f"INMET {ano}: baixando {url}")
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / f"{ano}.zip"
            try:
                ok = baixar(url, timeout=300, destino=zip_path)
            except RuntimeError as exc:
                print(f"  ERRO: {exc}")
                continue
            if ok is None:
                print("  pacote não encontrado (404)")
                continue
            try:
                diario, metas = inmet.processar_zip(zip_path, "SP")
            except Exception as exc:  # noqa: BLE001
                print(f"  ERRO ao processar: {exc}")
                continue
        if diario.empty:
            print("  nenhuma estação de SP no pacote")
            continue
        diario.to_csv(destino, index=False, float_format="%.4g", date_format="%Y-%m-%d", compression=GZIP)
        print(f"  {diario['codigo'].nunique()} estações, {len(diario)} dias")
        for m in metas:
            atual = catalogo.get(m["codigo"], {})
            atual.update({k: m[k] for k in ("codigo", "nome", "lat", "lon", "alt") if k in m})
            if m.get("fundacao"):
                atual["fundacao"] = m["fundacao"]
            atual["uf"] = "SP"
            catalogo[m["codigo"]] = atual

    # Período com dados de cada estação
    faixas: dict[str, list] = {}
    for arq in sorted(DIR_INMET_DIARIO.glob("inmet_sp_*.csv.gz")):
        df = pd.read_csv(arq, usecols=["codigo", "dia", "chuva_mm", "temp_c"], dtype={"codigo": str})
        df = df.dropna(subset=["chuva_mm", "temp_c"], how="all")
        for cod, g in df.groupby("codigo"):
            ini, fim = g["dia"].min(), g["dia"].max()
            f = faixas.setdefault(cod, [ini, fim])
            f[0], f[1] = min(f[0], ini), max(f[1], fim)
    for cod, (ini, fim) in faixas.items():
        if cod in catalogo:
            catalogo[cod]["inicio_dados"], catalogo[cod]["fim_dados"] = ini, fim

    inmet.salvar_estacoes(
        list(catalogo.values()),
        "Pacotes históricos do INMET (portal.inmet.gov.br/dadoshistoricos), atualizado em " + agora(),
    )
    marcar_atualizacao("inmet")


def marcar_atualizacao(chave: str) -> None:
    dados = ler_json(ARQ_ATUALIZACAO, {})
    dados[chave] = agora()
    gravar_json(ARQ_ATUALIZACAO, dados)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("alvo", choices=["esalq", "inmet", "tudo"])
    ap.add_argument("--anos", type=int, nargs="*", help="anos específicos")
    ap.add_argument("--desde", type=int, default=ANO_INICIAL_BUSCA_ESALQ, help="primeiro ano procurado na ESALQ")
    ap.add_argument("--forcar", action="store_true", help="baixa de novo mesmo os anos já completos")
    args = ap.parse_args()

    if args.alvo in ("esalq", "tudo"):
        atualizar_esalq(args.anos, args.desde, args.forcar)
    if args.alvo in ("inmet", "tudo"):
        atualizar_inmet(args.anos, args.forcar)


if __name__ == "__main__":
    main()
