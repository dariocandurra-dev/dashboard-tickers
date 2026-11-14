"""Configuracion central del proyecto."""
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
# El Excel historico viaja con el proyecto. Se puede apuntar a otra ubicacion
# con la variable de entorno TICKERS_XLSX.
RAW_XLSX = Path(os.getenv("TICKERS_XLSX", ROOT / "raw" / "Tickers.xlsx"))

MASTER_CSV = CONFIG_DIR / "tickers_master.csv"
PRICES_LONG = DATA_DIR / "prices_long.parquet"
PRICES_WIDE = DATA_DIR / "prices_wide.parquet"
BASE100 = DATA_DIR / "base100.parquet"
QA_REPORT = DATA_DIR / "qa_report.md"

# Fecha de inicio del panel. 01-ene-2020 fue feriado en todas las plazas:
# la primera rueda efectiva es el 02-ene-2020.
START_DATE = pd.Timestamp("2020-01-02")

# Excel serial date: dia 0 = 1899-12-30 (sistema 1900 con el bug de Lotus)
EXCEL_EPOCH = pd.Timestamp("1899-12-30")

# Umbrales de control de calidad
MAX_GAP_DAYS = 10          # hueco maximo tolerado dentro de una serie
MAX_DAILY_MOVE = 0.60      # variacion diaria >60% => posible split/error


def load_master() -> pd.DataFrame:
    """Devuelve el maestro de tickers con el mapeo corregido."""
    m = pd.read_csv(MASTER_CSV)
    m["sheet"] = m["sheet"].fillna("")
    return m
