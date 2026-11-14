"""
ETAPA 1 - Construccion de la capa de datos.

Flujo:
  1. Carga el maestro de tickers corregido.
  2. Parsea el historico del Excel (hojas validas).
  3. Repone via API las series faltantes o mal mapeadas (si hay red).
  4. Normaliza: calendario union, matriz ancha, base 100.
  5. Persiste en Parquet y emite un reporte de control de calidad.

Uso:
    python scripts/stage1_build.py            # con reposicion via API
    python scripts/stage1_build.py --offline  # solo lo que hay en el Excel
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config as C
from src import excel_loader, normalize

try:
    from src import api_loader
except ImportError:
    api_loader = None


def main(offline: bool = False) -> None:
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    master = C.load_master()
    print(f"[1/5] Maestro cargado: {len(master)} tickers")

    long = excel_loader.load_all(master)
    print(f"[2/5] Excel parseado: {long['ticker'].nunique()} series, {len(long):,} observaciones")

    # --- Reposicion via API -------------------------------------------------
    pendientes = master[master["status"].isin(["empty", "mismapped", "pending_migration"])]
    pares = [(r["ticker"], r["yf_symbol"]) for _, r in pendientes.iterrows()]
    if offline or api_loader is None:
        print(f"[3/5] Reposicion OMITIDA ({len(pares)} series pendientes)")
    else:
        print(f"[3/5] Reponiendo {len(pares)} series via API...")
        rep = api_loader.fetch_many(pares)
        if not rep.empty:
            long = long[~long["ticker"].isin(rep["ticker"].unique())]
            long = pd.concat([long, rep], ignore_index=True)
            print(f"      Repuestas {rep['ticker'].nunique()} series ({len(rep):,} obs)")

    long = long.sort_values(["ticker", "date"]).reset_index(drop=True)

    # --- Normalizacion ------------------------------------------------------
    wide = normalize.to_wide(long)
    b100_own = normalize.base_100(wide, start=None)
    b100_panel = normalize.base_100(wide, start=C.START_DATE)
    print(f"[4/5] Panel normalizado: {wide.shape[0]:,} ruedas x {wide.shape[1]} tickers")

    # --- Persistencia -------------------------------------------------------
    long.to_parquet(C.PRICES_LONG, index=False)
    wide.to_parquet(C.PRICES_WIDE)
    b100_panel.to_parquet(C.BASE100)
    b100_own.to_parquet(C.DATA_DIR / "base100_propio.parquet")

    qa = normalize.qa_checks(long, wide, C.MAX_GAP_DAYS, C.MAX_DAILY_MOVE)
    qa.to_csv(C.DATA_DIR / "qa_series.csv", index=False)

    faltan = sorted(set(master["ticker"]) - set(long["ticker"].unique()))
    write_report(master, long, wide, qa, faltan)
    print(f"[5/5] Persistido en {C.DATA_DIR}")
    if faltan:
        print(f"      PENDIENTES ({len(faltan)}): {', '.join(faltan)}")


def write_report(master, long, wide, qa, faltan) -> None:
    L = []
    L.append("# Etapa 1 - Reporte de calidad de datos\n")
    L.append(f"- Tickers en el maestro: **{len(master)}**")
    L.append(f"- Series con historico cargado: **{long['ticker'].nunique()}**")
    L.append(f"- Observaciones totales: **{len(long):,}**")
    L.append(f"- Ventana del panel: **{wide.index.min().date()} a {wide.index.max().date()}** "
             f"({len(wide):,} ruedas)\n")

    if faltan:
        L.append("## Series pendientes de reposicion\n")
        sub = master[master["ticker"].isin(faltan)]
        L.append(sub[["ticker", "empresa", "yf_symbol", "currency", "status", "nota"]]
                 .to_markdown(index=False))
        L.append("")

    L.append("## Series con moneda distinta de USD\n")
    nousd = master[master["currency"] != "USD"]
    L.append(nousd[["ticker", "empresa", "yf_symbol", "currency", "nota"]].to_markdown(index=False))
    L.append("")

    alertas = qa[(qa["gaps_sobre_umbral"] > 0) | (qa["saltos_extremos"] > 0)]
    L.append("## Series con anomalias detectadas\n")
    L.append(alertas.to_markdown(index=False) if len(alertas) else "_Ninguna._")
    L.append("")

    C.QA_REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true", help="no llamar a la API")
    main(**vars(p.parse_args()))
