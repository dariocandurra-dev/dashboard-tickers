"""
Armado de la ficha por accion: une el perfil fundamental, los KPIs y el estado
tecnico en un unico registro por ticker, que es lo que consume la UI.

Se resuelve aca y no en la interfaz a proposito: la ficha define que es un dato
faltante y como se muestra. Si esa logica queda en el front, cada componente
inventa su propia convencion y terminan conviviendo '-', 'N/D', 'nan' y 0 para
el mismo caso.
"""
from __future__ import annotations

import pandas as pd


def build(master: pd.DataFrame,
          perfiles: pd.DataFrame | None,
          kpis: pd.DataFrame | None,
          calendario: pd.DataFrame | None,
          snapshot: pd.DataFrame | None) -> pd.DataFrame:
    """Consolida una fila por ticker con todo lo necesario para la ficha."""
    f = master[["ticker", "empresa", "sector", "pais", "asset_type",
                "currency", "yf_symbol", "status"]].copy()

    for df, campos in (
        (perfiles, ["nombre", "hq", "sector_yf", "industria", "empleados",
                    "sitio_web", "moneda_reporte"]),
        (kpis, ["periodo_fiscal", "revenue", "revenue_yoy", "net_income",
                "margen_bruto", "margen_operativo", "margen_neto", "roe", "roa",
                "deuda_patrimonio", "free_cash_flow", "market_cap",
                "pe_trailing", "pe_forward", "price_to_book", "ev_ebitda",
                "dividend_yield"]),
        (calendario, ["proximo_balance", "balance_confirmado"]),
        (snapshot, ["date", "close", "sma50", "sma200", "dist_ma200",
                    "above_ma200_conf", "tendencia_larga", "macd_hist",
                    "rsi14", "rsi_zona", "vol20", "drawdown"]),
    ):
        if df is None or df.empty:
            continue
        cols = ["ticker"] + [c for c in campos if c in df.columns]
        f = f.merge(df[cols].drop_duplicates("ticker"), on="ticker", how="left")

    # El nombre del maestro manda; el de yfinance solo completa si falta
    if "nombre" in f.columns:
        f["nombre"] = f["nombre"].fillna("").replace("", pd.NA).fillna(f["empresa"])

    f["dias_a_balance"] = _dias_a_balance(f)
    f["completitud"] = _completitud(f)
    return f.sort_values("ticker").reset_index(drop=True)


def _dias_a_balance(f: pd.DataFrame) -> pd.Series:
    """Dias corridos hasta la proxima presentacion (negativo si ya paso)."""
    if "proximo_balance" not in f.columns:
        return pd.Series(pd.NA, index=f.index, dtype="Float64")
    prox = pd.to_datetime(f["proximo_balance"], errors="coerce")
    return (prox - pd.Timestamp.now().normalize()).dt.days.astype("Float64")


def _completitud(f: pd.DataFrame) -> pd.Series:
    """Fraccion de KPIs poblados: permite ordenar la grilla por confiabilidad."""
    campos = ["revenue", "net_income", "margen_neto", "roe",
              "market_cap", "pe_trailing"]
    presentes = [c for c in campos if c in f.columns]
    if not presentes:
        return pd.Series(0.0, index=f.index)
    return f[presentes].notna().sum(axis=1) / len(presentes)


def gaps(f: pd.DataFrame) -> pd.DataFrame:
    """Tickers con ficha incompleta, para priorizar el complemento de fuentes."""
    eq = f[f["asset_type"] == "EQUITY"]
    out = eq[eq["completitud"] < 1.0][
        ["ticker", "empresa", "pais", "yf_symbol", "completitud", "status"]]
    return out.sort_values("completitud")
