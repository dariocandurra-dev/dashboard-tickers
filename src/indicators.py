"""
ETAPA 2 - Indicadores tecnicos.

Todas las funciones operan sobre una Serie de cierres indexada por fecha y
devuelven Series o DataFrames alineados al mismo indice.

Decision de diseno importante: los indicadores se calculan sobre la serie
*observada* de cada ticker, no sobre la matriz ancha con forward-fill. Un dia
rellenado repite el cierre anterior, y sobre datos repetidos el MACD se aplana y
los cruces de media movil generan senales falsas (el precio "toca" la media sin
que haya habido rueda). Cada papel se procesa en su propio calendario y recien
al final se consolida.

El panel solo tiene cierres, no OHLCV. Eso descarta ATR, rango verdadero y todo
lo que dependa de volumen (OBV, VWAP, MFI). Como sustituto de volatilidad se usa
el desvio estandar anualizado de retornos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Parametros por defecto
SMA_WINDOWS = (20, 50, 100, 200)
EMA_WINDOWS = (12, 26, 50)
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
RSI_PERIOD = 14
BB_WINDOW, BB_STD = 20, 2.0
VOL_WINDOWS = (20, 60)
TRADING_DAYS = 252


def sma(close: pd.Series, window: int) -> pd.Series:
    """Media movil simple. Exige la ventana completa: sin ventana, sin valor."""
    return close.rolling(window=window, min_periods=window).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    """Media movil exponencial.

    adjust=False replica la formulacion recursiva estandar de las plataformas
    de trading. Se exige `span` observaciones minimas para no publicar valores
    de arranque inestables.
    """
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def macd(close: pd.Series, fast: int = MACD_FAST, slow: int = MACD_SLOW,
         signal: int = MACD_SIGNAL) -> pd.DataFrame:
    """MACD clasico (12, 26, 9).

    Devuelve la linea MACD (EMA rapida - EMA lenta), su linea de senal
    (EMA de la linea MACD) y el histograma (diferencia entre ambas).
    """
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({
        "macd": line,
        "macd_signal": sig,
        "macd_hist": line - sig,
    })


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """RSI con suavizado de Wilder (equivalente a EMA con alpha = 1/period)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # Si no hubo perdidas en toda la ventana, el RSI satura en 100
    return out.where(avg_loss.notna(), np.nan).fillna(
        pd.Series(np.where(avg_loss.eq(0.0), 100.0, np.nan), index=close.index)
    )


def bollinger(close: pd.Series, window: int = BB_WINDOW,
              n_std: float = BB_STD) -> pd.DataFrame:
    """Bandas de Bollinger y %B (posicion relativa del precio dentro del canal)."""
    mid = close.rolling(window, min_periods=window).mean()
    sd = close.rolling(window, min_periods=window).std(ddof=0)
    upper, lower = mid + n_std * sd, mid - n_std * sd
    width = (upper - lower) / mid
    pct_b = (close - lower) / (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame({
        "bb_mid": mid, "bb_upper": upper, "bb_lower": lower,
        "bb_width": width, "bb_pct_b": pct_b,
    })


def volatility(close: pd.Series, window: int) -> pd.Series:
    """Volatilidad anualizada: desvio de retornos logaritmicos x raiz de 252."""
    r = np.log(close / close.shift(1))
    return r.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(TRADING_DAYS)


def drawdown(close: pd.Series) -> pd.DataFrame:
    """Caida desde el maximo historico acumulado de la serie."""
    peak = close.cummax()
    return pd.DataFrame({
        "peak": peak,
        "drawdown": close / peak - 1.0,
    })


def drawdown_52s(close: pd.Series, window: int = TRADING_DAYS) -> pd.Series:
    """Caida desde el maximo de las ultimas 252 ruedas (un anio bursatil).

    Distinto del drawdown historico: mide el castigo del ultimo anio y no el
    de toda la serie, que es lo relevante para juzgar una caida actual.
    """
    return close / close.rolling(window, min_periods=1).max() - 1.0


def pendiente(ma: pd.Series, periodos: int = 20) -> pd.Series:
    """Variacion porcentual de una media en `periodos` ruedas.

    Separa el retroceso dentro de una tendencia alcista (media todavia
    subiendo) del cambio de tendencia (media ya girada), distincion que la
    distancia a la media por si sola no muestra.
    """
    return ma / ma.shift(periodos) - 1.0


def z_distancia(dist: pd.Series, vol: pd.Series) -> pd.Series:
    """Distancia a la media expresada en jornadas de volatilidad.

    Permite comparar papeles con volatilidades muy distintas: en este panel
    van de 4% a 246% anual, asi que un mismo porcentaje de distancia significa
    cosas muy diferentes segun el activo.

    Se usa la volatilidad de 60 ruedas: la de 20 se infla por la propia caida
    que se esta midiendo y termina disimulando los derrumbes.
    """
    diaria = vol / np.sqrt(TRADING_DAYS)
    return dist / diaria.where(diaria > 0)


def compute_all(close: pd.Series) -> pd.DataFrame:
    """Calcula el set completo de indicadores para una serie de cierres."""
    close = close.dropna().sort_index()
    out = pd.DataFrame({"close": close})

    for w in SMA_WINDOWS:
        out[f"sma{w}"] = sma(close, w)
    for w in EMA_WINDOWS:
        out[f"ema{w}"] = ema(close, w)

    out = out.join(macd(close))
    out["rsi14"] = rsi(close)
    out = out.join(bollinger(close))

    for w in VOL_WINDOWS:
        out[f"vol{w}"] = volatility(close, w)

    out = out.join(drawdown(close))

    # Distancia porcentual a la MA200: el insumo directo de la alerta tecnica
    out["dist_ma200"] = close / out["sma200"] - 1.0
    out["dist_ma50"] = close / out["sma50"] - 1.0
    # Spread MA50-MA200: positivo = golden cross vigente
    out["spread_ma50_200"] = out["sma50"] / out["sma200"] - 1.0

    # --- Contexto de tendencia: insumos del diagnostico tecnico ---
    out["dd52"] = drawdown_52s(close)
    out["pend_ma200"] = pendiente(out["sma200"], 20)
    out["z_ma200"] = z_distancia(out["dist_ma200"], out["vol60"])
    out["macd_hist_prev"] = out["macd_hist"].shift(1)

    return out


def compute_panel(long: pd.DataFrame) -> pd.DataFrame:
    """Aplica compute_all a cada ticker del panel y consolida en formato largo."""
    frames = []
    for tk, grp in long.groupby("ticker", sort=True):
        s = grp.set_index("date")["close"]
        df = compute_all(s)
        df.insert(0, "ticker", tk)
        frames.append(df.reset_index())
    return pd.concat(frames, ignore_index=True)
