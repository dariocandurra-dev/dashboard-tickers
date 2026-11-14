"""
Lector del Excel historico.

El archivo original es heterogeneo: la mayoria de las hojas trae el simbolo con
prefijo MIC en A1 ('XNAS:AAPL') y los encabezados reales en la fila 2; otras
(TECO2) traen encabezados en la fila 1; algunas suman una columna 'Base 100'
precalculada; y las fechas vienen como serial de Excel.

Este modulo aplana todo eso a un unico formato largo:
    ticker | date | close | source
"""
from __future__ import annotations

import pandas as pd

from .config import EXCEL_EPOCH, RAW_XLSX, START_DATE


def _detect_header(df: pd.DataFrame) -> tuple[int, str | None]:
    """Ubica la fila de encabezados y devuelve (fila_datos, simbolo_origen).

    Devuelve el indice de la primera fila de datos y el simbolo declarado en A1
    cuando existe (formato 'MIC:TICKER'), o None si la hoja arranca directo con
    los encabezados.
    """
    a1 = str(df.iloc[0, 0]).strip()
    if a1.lower() == "date":          # encabezado en la fila 1 (caso TECO2)
        return 1, None
    if ":" in a1:                     # 'XNAS:AAPL' en A1, encabezado en fila 2
        return 2, a1
    return 2, None


def read_sheet(xls: pd.ExcelFile, sheet: str, ticker: str) -> pd.DataFrame:
    """Lee una hoja y devuelve un DataFrame largo limpio (puede venir vacio)."""
    raw = pd.read_excel(xls, sheet, header=None)
    if raw.empty or raw.shape[0] < 2:
        return pd.DataFrame(columns=["ticker", "date", "close", "source"])

    start_row, src_symbol = _detect_header(raw)
    body = raw.iloc[start_row:, :2].copy()
    body.columns = ["date", "close"]

    # Serial de Excel -> fecha. Se descartan filas no numericas.
    body["date"] = pd.to_numeric(body["date"], errors="coerce")
    body["close"] = pd.to_numeric(body["close"], errors="coerce")
    body = body.dropna(subset=["date", "close"])
    body["date"] = EXCEL_EPOCH + pd.to_timedelta(body["date"], unit="D")

    body = body[body["date"] >= START_DATE]
    body = body[body["close"] > 0]
    body = body.drop_duplicates(subset="date", keep="last").sort_values("date")

    body["ticker"] = ticker
    body["source"] = src_symbol or f"xlsx:{sheet}"
    return body[["ticker", "date", "close", "source"]].reset_index(drop=True)


def load_all(master: pd.DataFrame) -> pd.DataFrame:
    """Recorre el maestro y consolida todas las hojas con historico valido."""
    xls = pd.ExcelFile(RAW_XLSX)
    frames = []
    for _, row in master.iterrows():
        sheet = row["sheet"]
        if not sheet or sheet not in xls.sheet_names:
            continue
        df = read_sheet(xls, sheet, row["ticker"])
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["ticker", "date", "close", "source"])
    return pd.concat(frames, ignore_index=True)
