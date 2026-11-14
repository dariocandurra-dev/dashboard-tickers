"""
Repone via API unicamente las 12 series faltantes o mal mapeadas y las integra
al panel ya construido, sin reprocesar el Excel entero.

Uso:
    python scripts/repair_missing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config as C
from src import api_loader, normalize


def main() -> None:
    master = C.load_master()
    long = pd.read_parquet(C.PRICES_LONG)

    # Tres casos a reponer con historico completo:
    #   - series que nunca se cargaron (hoja vacia o ticker agregado despues)
    #   - series mal mapeadas en el Excel
    #   - series 'stale': el Excel las traia cortadas y de otra plaza, asi que
    #     empalmarles ruedas nuevas mezclaria dos fuentes. Se reemplazan una
    #     sola vez: cuando la fuente ya es la API, no se vuelven a bajar.
    cargados = set(long["ticker"].unique())
    fuente = long.groupby("ticker")["source"].last().to_dict()
    pares = []
    for _, r in master.iterrows():
        tk = r["ticker"]
        if tk not in cargados:
            pares.append((tk, r["yf_symbol"]))
        elif r["status"] in ("stale", "pending_migration") \
                and not str(fuente.get(tk, "")).startswith("yf:"):
            pares.append((tk, r["yf_symbol"]))

    if not pares:
        print("No hay series pendientes.")
        return

    print(f"Reponiendo {len(pares)} series:")
    rep = api_loader.fetch_many(pares)
    if rep.empty:
        print("No se pudo descargar ninguna serie. Revisar conectividad.")
        return

    long = long[~long["ticker"].isin(rep["ticker"].unique())]
    long = pd.concat([long, rep], ignore_index=True).sort_values(["ticker", "date"])

    wide = normalize.to_wide(long)
    long.to_parquet(C.PRICES_LONG, index=False)
    wide.to_parquet(C.PRICES_WIDE)
    normalize.base_100(wide, start=C.START_DATE).to_parquet(C.BASE100)
    normalize.base_100(wide, start=None).to_parquet(C.DATA_DIR / "base100_propio.parquet")

    qa = normalize.qa_checks(long, wide, C.MAX_GAP_DAYS, C.MAX_DAILY_MOVE)
    qa.to_csv(C.DATA_DIR / "qa_series.csv", index=False)

    print(f"\nPanel actualizado: {wide.shape[1]} tickers, {len(wide):,} ruedas")
    faltan = sorted(set(master['ticker']) - set(long['ticker'].unique()))
    print(f"Pendientes: {faltan if faltan else 'ninguno'}")


if __name__ == "__main__":
    main()
