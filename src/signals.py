"""
Deteccion de senales y estados a partir de los indicadores.

Separa dos conceptos que conviene no mezclar:

  - ESTADO: condicion vigente hoy (el precio esta por debajo de la MA200,
    el MACD esta en zona positiva, el RSI esta sobrecomprado). Sirve para
    filtrar y ordenar el panel.
  - EVENTO: el cruce puntual que cambio el estado en una rueda determinada.
    Es lo que dispara la alerta.

La alerta pedida — precio cruzando por debajo de la MA200 — es un EVENTO, no un
estado. Un papel que lleva ocho meses debajo de la MA200 no deberia notificar
todos los dias; solo el dia que cruzo. Por eso `days_since_cross` acompana a
cada estado: permite decidir la ventana de notificacion en la Etapa 4.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0

# Banda de confirmacion para el cruce de MA200 (ver _state_hysteresis)
CONFIRM_BAND = 0.01


def _state_hysteresis(price: pd.Series, ma: pd.Series,
                      band: float = CONFIRM_BAND) -> pd.Series:
    """Estado 'precio sobre la media' con histeresis, tipo disparador Schmitt.

    El cruce simple genera whipsaw: un papel que cotiza pegado a su MA200 la
    perfora y la recupera varias veces en la misma semana, y cada oscilacion
    dispara una alerta. Con histeresis el estado solo pasa a 'debajo' cuando el
    precio cierra por debajo de ma*(1-band), y solo vuelve a 'arriba' cuando
    supera ma*(1+band). Dentro de la banda el estado anterior se mantiene.

    Con band=0 el comportamiento es identico al cruce simple.
    """
    valid = price.notna() & ma.notna()
    lower = ma * (1.0 - band)
    upper = ma * (1.0 + band)

    p = price.to_numpy(dtype="float64")
    lo = lower.to_numpy(dtype="float64")
    up = upper.to_numpy(dtype="float64")
    ok = valid.to_numpy()

    out = np.full(len(p), np.nan, dtype="float64")
    state: bool | None = None
    for i in range(len(p)):
        if not ok[i]:
            continue
        if state is None:                 # arranque: se ancla al lado de la media
            state = bool(p[i] > (lo[i] + up[i]) / 2.0)
        elif state and p[i] < lo[i]:      # venia arriba y perforo la banda inferior
            state = False
        elif (not state) and p[i] > up[i]:  # venia abajo y supero la banda superior
            state = True
        out[i] = 1.0 if state else 0.0

    return pd.Series(out, index=price.index).map({1.0: True, 0.0: False}).astype("boolean")


def _state(a: pd.Series, b: pd.Series) -> pd.Series:
    """Booleano nulable 'a > b', con NA donde alguna de las dos no esta definida.

    El enmascarado importa: una comparacion contra NaN devuelve False, no nulo.
    Sin la mascara, el dia en que la MA200 empieza a existir la serie salta de
    False a True y se registra un cruce alcista que nunca ocurrio.
    """
    valid = a.notna() & b.notna()
    return (a > b).astype("boolean").where(valid)


def _cross(state: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Dado un estado booleano nulable, devuelve (cruce_alcista, cruce_bajista).

    Hay cruce cuando el estado cambia entre dos ruedas consecutivas, ambas con
    dato valido. El primer punto de la serie nunca es cruce.

    Se trabaja con dtype 'boolean' (nulable) y no con object: sobre una Serie
    object el operador ~ aplica negacion bit a bit de enteros (~True == -2, que
    evalua como verdadero) y todas las ruedas quedan marcadas como cruce.
    """
    state = state.astype("boolean")
    prev = state.shift(1).astype("boolean")
    up = (state & ~prev).fillna(False).astype(bool)
    down = (~state & prev).fillna(False).astype(bool)
    return up, down


def _days_since(flag: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Ruedas transcurridas desde el ultimo True (NaN si nunca ocurrio)."""
    pos = pd.Series(np.arange(len(flag)), index=flag.index)
    last = pos.where(flag).ffill()
    return (pos - last).where(last.notna())


def detect(ind: pd.DataFrame) -> pd.DataFrame:
    """Calcula estados y eventos para un ticker (DataFrame indexado por fecha)."""
    df = ind.sort_index()
    out = pd.DataFrame(index=df.index)

    # --- MA200: el nucleo de la alerta tecnica ---
    above200 = _state(df["close"], df["sma200"])
    up200, down200 = _cross(above200)
    out["above_ma200"] = above200
    out["cross_up_ma200"] = up200
    out["cross_down_ma200"] = down200
    out["dias_desde_cruce_ma200"] = _days_since(up200 | down200, df.index)

    # Version confirmada: la que alimenta la alerta, para no notificar whipsaw
    conf200 = _state_hysteresis(df["close"], df["sma200"])
    up200c, down200c = _cross(conf200)
    out["above_ma200_conf"] = conf200
    out["cross_up_ma200_conf"] = up200c
    out["cross_down_ma200_conf"] = down200c
    out["dias_desde_cruce_ma200_conf"] = _days_since(up200c | down200c, df.index)

    # --- MA50 y golden / death cross ---
    out["above_ma50"] = _state(df["close"], df["sma50"])
    gold_state = _state(df["sma50"], df["sma200"])
    golden, death = _cross(gold_state)
    out["golden_cross"] = golden
    out["death_cross"] = death
    out["tendencia_larga"] = gold_state.map(
        {True: "alcista", False: "bajista"}).astype("object")

    # --- MACD ---
    macd_pos = _state(df["macd"], df["macd_signal"])
    macd_up, macd_down = _cross(macd_pos)
    out["macd_alcista"] = macd_pos
    out["macd_cruce_alcista"] = macd_up
    out["macd_cruce_bajista"] = macd_down
    out["macd_sobre_cero"] = (df["macd"] > 0).astype("boolean").where(df["macd"].notna())
    out["dias_desde_cruce_macd"] = _days_since(macd_up | macd_down, df.index)

    # --- RSI ---
    zona = pd.Series(pd.NA, index=df.index, dtype="object")
    r = df["rsi14"]
    zona[r.notna()] = "neutral"
    zona[r >= RSI_OVERBOUGHT] = "sobrecompra"
    zona[r <= RSI_OVERSOLD] = "sobreventa"
    out["rsi_zona"] = zona

    return out


def detect_panel(ind_long: pd.DataFrame) -> pd.DataFrame:
    """Aplica la deteccion a todo el panel en formato largo."""
    frames = []
    for tk, grp in ind_long.groupby("ticker", sort=True):
        g = grp.set_index("date").drop(columns=["ticker"])
        sig = detect(g)
        sig.insert(0, "ticker", tk)
        frames.append(sig.reset_index())
    return pd.concat(frames, ignore_index=True)


def snapshot(ind_long: pd.DataFrame, sig_long: pd.DataFrame,
             master: pd.DataFrame) -> pd.DataFrame:
    """Foto del ultimo dia de cada serie: la tabla que consume el dashboard."""
    last_ind = ind_long.sort_values("date").groupby("ticker").tail(1)
    last_sig = sig_long.sort_values("date").groupby("ticker").tail(1)

    snap = last_ind.merge(last_sig.drop(columns=["date"]), on="ticker", how="left")
    snap = snap.merge(
        master[["ticker", "empresa", "sector", "pais", "currency", "status"]],
        on="ticker", how="left")

    cols = ["ticker", "empresa", "sector", "pais", "currency", "date", "close",
            "sma50", "sma200", "dist_ma200", "above_ma200", "above_ma200_conf",
            "cross_down_ma200_conf", "dias_desde_cruce_ma200_conf", "tendencia_larga", "macd", "macd_signal",
            "macd_hist", "macd_hist_prev", "macd_alcista", "macd_cruce_bajista",
            "rsi14", "rsi_zona", "vol20", "vol60", "drawdown",
            "dd52", "pend_ma200", "z_ma200", "status"]
    return snap[[c for c in cols if c in snap.columns]].sort_values("ticker")


def recent_events(sig_long: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """Eventos de cruce ocurridos en las ultimas `window` ruedas del panel."""
    cutoff = sig_long["date"].max() - pd.Timedelta(days=window * 2)
    recent = sig_long[sig_long["date"] >= cutoff]

    ev_cols = ["cross_down_ma200_conf", "cross_up_ma200_conf", "golden_cross",
               "death_cross", "macd_cruce_alcista", "macd_cruce_bajista"]
    rows = []
    for col in ev_cols:
        hit = recent[recent[col].fillna(False)]
        for _, r in hit.iterrows():
            rows.append({"ticker": r["ticker"], "date": r["date"], "evento": col})
    if not rows:
        return pd.DataFrame(columns=["ticker", "date", "evento"])
    return pd.DataFrame(rows).sort_values(["date", "ticker"], ascending=[False, True])
