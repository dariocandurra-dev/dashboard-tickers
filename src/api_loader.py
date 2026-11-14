"""
Capa de acceso a la API de precios (yfinance como fuente primaria).

Cumple dos funciones:
  1. Reposicion: bajar el historico completo de las series faltantes o rotas.
  2. Actualizacion incremental: traer solo lo posterior a la ultima fecha
     ya persistida, para el refresh diario.

Requiere salida a red hacia query1/query2.finance.yahoo.com.
"""
from __future__ import annotations

import time
import pandas as pd

from .config import START_DATE

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

RETRIES = 3
PAUSE = 1.5


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["ticker", "date", "close", "source"])


def fetch_one(ticker: str, yf_symbol: str, start=START_DATE, end=None) -> pd.DataFrame:
    """Descarga OHLCV de un simbolo y devuelve el formato largo canonico.

    Se usa el cierre ajustado por splits y dividendos (auto_adjust=True), que es
    lo correcto para indicadores tecnicos y para comparaciones en base 100.
    """
    if yf is None:
        raise ImportError("yfinance no esta instalado: pip install yfinance")

    for attempt in range(1, RETRIES + 1):
        try:
            df = yf.download(
                yf_symbol, start=start, end=end,
                auto_adjust=True, progress=False, threads=False,
            )
            if df is None or df.empty:
                raise ValueError("respuesta vacia")

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            out = df.reset_index()[["Date", "Close"]]
            out.columns = ["date", "close"]
            out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
            out["ticker"] = ticker
            out["source"] = f"yf:{yf_symbol}"
            out = out.dropna(subset=["close"])
            return out[["ticker", "date", "close", "source"]]

        except Exception as exc:  # red, rate limit o simbolo inexistente
            if attempt == RETRIES:
                print(f"  [FALLO] {ticker} ({yf_symbol}): {exc}")
                return _empty()
            time.sleep(PAUSE * attempt)
    return _empty()


def fetch_many(pairs: list[tuple[str, str]], start=START_DATE) -> pd.DataFrame:
    """Descarga en lote. `pairs` es una lista de (ticker_canonico, yf_symbol)."""
    frames = []
    for ticker, symbol in pairs:
        print(f"  -> {ticker:<6} via {symbol}")
        df = fetch_one(ticker, symbol, start=start)
        if not df.empty:
            frames.append(df)
        time.sleep(0.4)  # cortesia con la API
    return pd.concat(frames, ignore_index=True) if frames else _empty()


def fetch_incremental(master: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    """Trae solo las ruedas posteriores al ultimo dato de cada serie."""
    last = existing.groupby("ticker")["date"].max()
    frames = []
    for _, row in master.iterrows():
        tk, sym = row["ticker"], row["yf_symbol"]
        start = last.get(tk, START_DATE)
        start = pd.Timestamp(start) + pd.Timedelta(days=1)
        if start.normalize() > pd.Timestamp.today().normalize():
            continue
        df = fetch_one(tk, sym, start=start)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else _empty()
