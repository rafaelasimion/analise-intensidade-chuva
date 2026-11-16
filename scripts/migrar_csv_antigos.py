"""Converte os CSVs da versão Streamlit (dados/dados_AAAA.csv) para o formato novo.

O formato antigo só guardava a chuva. O formato novo
(dados/esalq/esalq_AAAA.csv.gz) tem todas as variáveis; as que não existiam
ficam vazias até o `atualizar_dados.py` baixar os arquivos completos da ESALQ.

Uso:  python scripts/migrar_csv_antigos.py [--apagar-antigos]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hidro.config import COLUNAS_15MIN, DIR_DADOS, DIR_ESALQ  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apagar-antigos", action="store_true", help="remove dados/dados_AAAA.csv depois de converter")
    args = ap.parse_args()

    antigos = sorted(DIR_DADOS.glob("dados_*.csv"))
    if not antigos:
        print("Nenhum CSV antigo encontrado.")
        return

    partes = []
    for arq in antigos:
        df = pd.read_csv(arq, usecols=["TIMESTAMP", "Chuva_mm"])
        df["data_hora"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce", format="ISO8601")
        partes.append(df[["data_hora", "Chuva_mm"]].rename(columns={"Chuva_mm": "chuva_mm"}))
        print(f"lido {arq.name}: {len(df)} linhas")

    tudo = pd.concat(partes, ignore_index=True).dropna(subset=["data_hora"])
    tudo = tudo.sort_values("data_hora").drop_duplicates("data_hora", keep="last")
    for c in COLUNAS_15MIN:
        if c not in tudo:
            tudo[c] = float("nan")
    tudo = tudo[COLUNAS_15MIN]

    DIR_ESALQ.mkdir(parents=True, exist_ok=True)
    for ano, parte in tudo.groupby(tudo["data_hora"].dt.year):
        destino = DIR_ESALQ / f"esalq_{ano}.csv.gz"
        if destino.exists():
            existente = pd.read_csv(destino, parse_dates=["data_hora"])
            if existente[[c for c in COLUNAS_15MIN[2:] if c in existente]].notna().any().any():
                print(f"{destino.name} já tem dados completos – mantido")
                continue
        parte.to_csv(destino, index=False, float_format="%.4g", date_format="%Y-%m-%d %H:%M:%S",
                     compression={"method": "gzip", "compresslevel": 9, "mtime": 0})
        print(f"gravado {destino.name}: {len(parte)} registros")

    if args.apagar_antigos:
        for arq in antigos:
            arq.unlink()
            print(f"removido {arq.name}")


if __name__ == "__main__":
    main()
