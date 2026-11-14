"""
ETAPA 3 - Datos fundamentales y KPIs (fuente: yfinance).

Tres bloques independientes, porque fallan por separado y conviene que un fallo
no arrastre a los demas:

  perfil    -> identidad de la empresa: nombre, sede, sector, industria, empleados
  kpis      -> ultimos revenues, ganancias, margenes y ratios de valuacion
  calendario-> proxima fecha de presentacion de balance

Dos advertencias sobre yfinance que condicionan el diseno:

1. Las etiquetas de los estados contables NO son estables. Segun el emisor y la
   version de la libreria, la linea de ingresos aparece como 'Total Revenue',
   'TotalRevenue' u 'Operating Revenue'. Por eso toda extraccion pasa por
   `_pick`, que prueba una lista de alias en orden y devuelve el primero que
   encuentra, en vez de indexar por una etiqueta fija.

2. La moneda de reporte puede diferir de la moneda de cotizacion. Un ADR cotiza
   en USD pero reporta en su moneda local (ICICI en INR, Toyota en JPY). Se
   guarda `financial_currency` junto a cada cifra: mezclar revenues de distinta
   moneda en un mismo ranking es un error silencioso.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

RETRIES = 3
PAUSE = 1.0

# --- Alias de lineas contables, en orden de preferencia --------------------
REVENUE = ["Total Revenue", "TotalRevenue", "Operating Revenue", "OperatingRevenue"]
GROSS_PROFIT = ["Gross Profit", "GrossProfit"]
OPERATING_INCOME = ["Operating Income", "OperatingIncome", "EBIT"]
NET_INCOME = ["Net Income", "NetIncome",
              "Net Income Common Stockholders",
              "Net Income From Continuing Operation Net Minority Interest"]
EBITDA = ["EBITDA", "Normalized EBITDA", "NormalizedEBITDA"]
TOTAL_ASSETS = ["Total Assets", "TotalAssets"]
TOTAL_EQUITY = ["Stockholders Equity", "StockholdersEquity",
                "Total Stockholder Equity", "Common Stock Equity"]
TOTAL_DEBT = ["Total Debt", "TotalDebt"]
FCF = ["Free Cash Flow", "FreeCashFlow"]
OCF = ["Operating Cash Flow", "OperatingCashFlow",
       "Total Cash From Operating Activities"]


def _pick(df: pd.DataFrame | None, aliases: list[str], col: int = 0) -> float:
    """Busca la primera etiqueta disponible de la lista y devuelve su valor.

    `col=0` es el periodo mas reciente (yfinance ordena las columnas de mas nuevo
    a mas viejo). Devuelve NaN si ninguna etiqueta existe o el valor es nulo.
    """
    if df is None or df.empty or col >= df.shape[1]:
        return np.nan
    idx = {str(i).strip().lower(): i for i in df.index}
    for alias in aliases:
        key = alias.strip().lower()
        if key in idx:
            val = df.loc[idx[key]].iloc[col]
            if pd.notna(val):
                return float(val)
    return np.nan


def _safe_div(a: float, b: float) -> float:
    """Division que devuelve NaN ante denominador nulo, cero o ausente."""
    if pd.isna(a) or pd.isna(b) or b == 0:
        return np.nan
    return a / b


def _get(info: dict, *keys, default=np.nan) -> Any:
    """Primer valor no nulo entre varias claves posibles del dict `info`."""
    for k in keys:
        v = info.get(k)
        if v is not None and v != "":
            return v
    return default


# --- Extractores ----------------------------------------------------------

def extract_profile(ticker: str, info: dict) -> dict:
    """Ficha de identidad: nombre, sede, sector, industria, tamano."""
    city = _get(info, "city", default="")
    state = _get(info, "state", default="")
    country = _get(info, "country", default="")
    hq = ", ".join([p for p in (city, state, country) if p])

    return {
        "ticker": ticker,
        "nombre": _get(info, "longName", "shortName", default=""),
        "hq": hq,
        "hq_ciudad": city,
        "hq_pais": country,
        "sector_yf": _get(info, "sector", default=""),
        "industria": _get(info, "industry", default=""),
        "empleados": _get(info, "fullTimeEmployees"),
        "sitio_web": _get(info, "website", default=""),
        "descripcion": _get(info, "longBusinessSummary", default=""),
        "moneda_cotizacion": _get(info, "currency", default=""),
        "moneda_reporte": _get(info, "financialCurrency", default=""),
    }


def extract_kpis(ticker: str, info: dict,
                 income: pd.DataFrame | None,
                 balance: pd.DataFrame | None,
                 cashflow: pd.DataFrame | None) -> dict:
    """Ultimos resultados anuales, margenes y ratios.

    Los margenes se recalculan desde los estados contables en vez de tomar
    `profitMargins` de `info`: ese campo es TTM y no siempre coincide con el
    ultimo ejercicio cerrado, lo que produce inconsistencias contra los
    revenues que se muestran al lado.
    """
    rev = _pick(income, REVENUE)
    rev_prev = _pick(income, REVENUE, col=1)
    gross = _pick(income, GROSS_PROFIT)
    op = _pick(income, OPERATING_INCOME)
    net = _pick(income, NET_INCOME)
    ebitda = _pick(income, EBITDA)

    assets = _pick(balance, TOTAL_ASSETS)
    equity = _pick(balance, TOTAL_EQUITY)
    debt = _pick(balance, TOTAL_DEBT)

    fcf = _pick(cashflow, FCF)
    ocf = _pick(cashflow, OCF)

    periodo = ""
    if income is not None and not income.empty:
        periodo = str(pd.Timestamp(income.columns[0]).date())

    return {
        "ticker": ticker,
        "periodo_fiscal": periodo,
        "moneda_reporte": _get(info, "financialCurrency", default=""),
        # --- Resultados ---
        "revenue": rev,
        "revenue_prev": rev_prev,
        "revenue_yoy": _safe_div(rev - rev_prev, rev_prev) if pd.notna(rev_prev) else np.nan,
        "gross_profit": gross,
        "operating_income": op,
        "net_income": net,
        "ebitda": ebitda,
        # --- Margenes (recalculados) ---
        "margen_bruto": _safe_div(gross, rev),
        "margen_operativo": _safe_div(op, rev),
        "margen_neto": _safe_div(net, rev),
        "margen_ebitda": _safe_div(ebitda, rev),
        # --- Retornos y estructura ---
        "roe": _safe_div(net, equity),
        "roa": _safe_div(net, assets),
        "deuda_patrimonio": _safe_div(debt, equity),
        "free_cash_flow": fcf,
        "operating_cash_flow": ocf,
        "conversion_fcf": _safe_div(fcf, net),
        # --- Valuacion (de info, es de mercado y por lo tanto TTM) ---
        "market_cap": _get(info, "marketCap"),
        "pe_trailing": _get(info, "trailingPE"),
        "pe_forward": _get(info, "forwardPE"),
        "price_to_book": _get(info, "priceToBook"),
        "ev_ebitda": _get(info, "enterpriseToEbitda"),
        "dividend_yield": _get(info, "dividendYield"),
        "beta": _get(info, "beta"),
        "eps_trailing": _get(info, "trailingEps"),
    }


def extract_calendar(ticker: str, tk_obj) -> dict:
    """Proxima fecha de presentacion de balance.

    yfinance expone `calendar` como dict o DataFrame segun version; se
    contemplan ambas formas.
    """
    out = {"ticker": ticker, "proximo_balance": pd.NaT,
           "balance_confirmado": False, "eps_estimado": np.nan}
    try:
        cal = tk_obj.calendar
    except Exception:
        return out

    fechas = []
    if isinstance(cal, dict):
        v = cal.get("Earnings Date")
        fechas = v if isinstance(v, (list, tuple)) else ([v] if v else [])
        out["eps_estimado"] = cal.get("Earnings Average", np.nan)
    elif isinstance(cal, pd.DataFrame) and not cal.empty:
        if "Earnings Date" in cal.index:
            fechas = list(cal.loc["Earnings Date"].dropna())

    fechas = [pd.Timestamp(f) for f in fechas if f is not None and pd.notna(f)]
    if fechas:
        out["proximo_balance"] = min(fechas)
        # Un unico valor implica fecha confirmada; un rango, fecha estimada
        out["balance_confirmado"] = len(fechas) == 1
    return out


# --- Descarga -------------------------------------------------------------

def fetch_one(ticker: str, yf_symbol: str, es_etf: bool = False) -> dict:
    """Descarga los tres bloques de un simbolo. Nunca lanza: reporta en 'error'."""
    if yf is None:
        raise ImportError("yfinance no esta instalado")

    res = {"perfil": None, "kpis": None, "calendario": None, "error": ""}
    for attempt in range(1, RETRIES + 1):
        try:
            t = yf.Ticker(yf_symbol)
            info = t.info or {}
            if not info:
                raise ValueError("info vacio")

            res["perfil"] = extract_profile(ticker, info)

            if es_etf:
                # Un ETF no tiene estados contables: se guarda lo que si aplica
                res["kpis"] = {
                    "ticker": ticker, "es_etf": True,
                    "moneda_reporte": _get(info, "currency", default=""),
                    "aum": _get(info, "totalAssets"),
                    "expense_ratio": _get(info, "annualReportExpenseRatio",
                                          "netExpenseRatio"),
                    "dividend_yield": _get(info, "yield", "dividendYield"),
                    "beta": _get(info, "beta3Year", "beta"),
                }
            else:
                res["kpis"] = extract_kpis(
                    ticker, info,
                    _safe_stmt(t, "income_stmt"),
                    _safe_stmt(t, "balance_sheet"),
                    _safe_stmt(t, "cashflow"),
                )
                res["kpis"]["es_etf"] = False

            res["calendario"] = extract_calendar(ticker, t)
            return res

        except Exception as exc:
            if attempt == RETRIES:
                res["error"] = f"{type(exc).__name__}: {exc}"
                return res
            time.sleep(PAUSE * attempt)
    return res


def _safe_stmt(t, attr: str) -> pd.DataFrame | None:
    """Accede a un estado contable tolerando que la propiedad falle o venga vacia."""
    try:
        df = getattr(t, attr)
        return df if isinstance(df, pd.DataFrame) and not df.empty else None
    except Exception:
        return None


def fetch_many(rows: list[tuple[str, str, bool]]) -> dict[str, pd.DataFrame]:
    """Descarga en lote. `rows` es una lista de (ticker, yf_symbol, es_etf)."""
    perfiles, kpis, cals, errores = [], [], [], []
    for ticker, symbol, es_etf in rows:
        r = fetch_one(ticker, symbol, es_etf)
        if r["error"]:
            errores.append({"ticker": ticker, "symbol": symbol, "error": r["error"]})
            print(f"  [FALLO] {ticker}: {r['error'][:70]}")
            continue
        perfiles.append(r["perfil"])
        kpis.append(r["kpis"])
        cals.append(r["calendario"])
        time.sleep(0.3)

    return {
        "perfiles": pd.DataFrame(perfiles),
        "kpis": pd.DataFrame(kpis),
        "calendario": pd.DataFrame(cals),
        "errores": pd.DataFrame(errores),
    }
