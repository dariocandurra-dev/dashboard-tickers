"""
Normalizacion del panel: calendario comun, matriz ancha y series base 100.

Criterio de calendario: se toma la union de ruedas efectivamente observadas en
el panel (no un calendario teorico de dias habiles), porque conviven plazas con
feriados distintos (NYSE, Nasdaq, BYMA, XETR, NSE). Dentro de la vida de cada
serie los huecos se rellenan hacia adelante (ultimo cierre conocido); antes del
primer dato y despues del ultimo, la serie queda en NaN. Asi una accion que
listo en 2021 no arrastra precios ficticios en 2020.
"""
from __future__ import annotations

import pandas as pd


def to_wide(long: pd.DataFrame, ffill: bool = True) -> pd.DataFrame:
    """Pivotea a matriz fecha x ticker sobre el calendario union del panel."""
    wide = long.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
    wide = wide.sort_index()

    if ffill:
        filled = wide.ffill()
        # Se enmascara todo lo anterior al primer dato real y posterior al ultimo
        valid = wide.notna()
        first = valid.idxmax()
        last = valid[::-1].idxmax()
        for col in wide.columns:
            if not valid[col].any():
                continue
            mask = (wide.index >= first[col]) & (wide.index <= last[col])
            filled.loc[~mask, col] = pd.NA
        wide = filled

    return wide.astype("float64")


def base_100(wide: pd.DataFrame, start=None) -> pd.DataFrame:
    """Rebasea cada serie a 100.

    Si `start` es None, cada serie se rebasea en su propio primer dato valido
    (util para comparar performance desde el listado de cada papel). Si se pasa
    una fecha, todas se rebasean en la primera rueda >= start, y las series que
    todavia no cotizaban quedan en NaN hasta su debut.
    """
    if start is None:
        base = wide.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else pd.NA)
    else:
        start = pd.Timestamp(start)
        sub = wide.loc[wide.index >= start]
        base = sub.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else pd.NA)
        wide = sub

    base = pd.to_numeric(base, errors="coerce")
    return wide.div(base, axis=1).mul(100.0)


def returns(wide: pd.DataFrame, log: bool = False) -> pd.DataFrame:
    """Retornos diarios simples o logaritmicos."""
    import numpy as np
    if log:
        return np.log(wide / wide.shift(1))
    return wide.pct_change()


def qa_checks(long: pd.DataFrame, wide: pd.DataFrame,
              max_gap_days: int, max_daily_move: float) -> pd.DataFrame:
    """Control de calidad por serie: cobertura, huecos y saltos sospechosos."""
    rets = returns(wide)
    rows = []
    for tk in sorted(long["ticker"].unique()):
        s = long[long["ticker"] == tk].sort_values("date")
        gaps = s["date"].diff().dt.days
        r = rets[tk].dropna() if tk in rets.columns else pd.Series(dtype=float)
        rows.append({
            "ticker": tk,
            "n_obs": len(s),
            "desde": s["date"].min().date(),
            "hasta": s["date"].max().date(),
            "gap_max_dias": int(gaps.max()) if len(gaps.dropna()) else 0,
            "gaps_sobre_umbral": int((gaps > max_gap_days).sum()),
            "saltos_extremos": int((r.abs() > max_daily_move).sum()),
            "fuente": s["source"].iloc[-1],
        })
    return pd.DataFrame(rows)
