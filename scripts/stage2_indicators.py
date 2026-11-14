"""
ETAPA 2 - Calculo de indicadores tecnicos y senales sobre el panel.

Uso:
    python scripts/stage2_indicators.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config as C
from src import indicators, signals

IND_PARQUET = C.DATA_DIR / "indicators.parquet"
SIG_PARQUET = C.DATA_DIR / "signals.parquet"
SNAP_CSV = C.DATA_DIR / "snapshot_tecnico.csv"
EVENTS_CSV = C.DATA_DIR / "eventos_recientes.csv"


def main() -> None:
    master = C.load_master()
    long = pd.read_parquet(C.PRICES_LONG)
    print(f"[1/4] Panel: {long['ticker'].nunique()} series, {len(long):,} obs")

    ind = indicators.compute_panel(long)
    print(f"[2/4] Indicadores calculados: {ind.shape[1] - 2} columnas")

    sig = signals.detect_panel(ind)
    print(f"[3/4] Senales detectadas")

    snap = signals.snapshot(ind, sig, master)
    events = signals.recent_events(sig, window=10)

    ind.to_parquet(IND_PARQUET, index=False)
    sig.to_parquet(SIG_PARQUET, index=False)
    snap.to_csv(SNAP_CSV, index=False)
    events.to_csv(EVENTS_CSV, index=False)
    print(f"[4/4] Persistido en {C.DATA_DIR}")

    # --- Resumen operativo ---
    con_ma200 = snap["sma200"].notna().sum()
    debajo = int((~snap["above_ma200"].fillna(True)).sum())
    print(f"\nCobertura MA200: {con_ma200}/{len(snap)} series")
    print(f"Por debajo de la MA200: {debajo}")
    print(f"Tendencia larga alcista: {int((snap['tendencia_larga'] == 'alcista').sum())}")
    print(f"MACD alcista: {int(snap['macd_alcista'].fillna(False).sum())}")
    print(f"Eventos de cruce en las ultimas 10 ruedas: {len(events)}")


if __name__ == "__main__":
    main()
