"""
Validacion de la capa fundamental sin salir a la red.

Los fixtures replican la forma real de los objetos de yfinance, incluyendo los
casos que rompen un parser ingenuo:

  - etiquetas alternativas ('TotalRevenue' pegado vs 'Total Revenue')
  - lineas contables ausentes (bancos sin 'Gross Profit')
  - patrimonio negativo (el ROE debe salir negativo, no explotar)
  - moneda de reporte distinta de la de cotizacion (ADR)
  - ETFs sin estados contables

Uso:  python tests/test_fundamentals.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import fundamentals as F

COLS = [pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31")]

# --- Fixture 1: empresa estandar, etiquetas canonicas ---------------------
INCOME_OK = pd.DataFrame(
    {COLS[0]: [400_000, 180_000, 120_000, 95_000, 140_000],
     COLS[1]: [350_000, 155_000, 100_000, 78_000, 118_000]},
    index=["Total Revenue", "Gross Profit", "Operating Income",
           "Net Income", "EBITDA"])

BALANCE_OK = pd.DataFrame(
    {COLS[0]: [500_000, 200_000, 90_000], COLS[1]: [450_000, 170_000, 85_000]},
    index=["Total Assets", "Stockholders Equity", "Total Debt"])

CASHFLOW_OK = pd.DataFrame(
    {COLS[0]: [85_000, 110_000], COLS[1]: [70_000, 95_000]},
    index=["Free Cash Flow", "Operating Cash Flow"])

# --- Fixture 2: etiquetas pegadas y lineas faltantes (caso banco) ---------
INCOME_ALT = pd.DataFrame(
    {COLS[0]: [90_000, 30_000], COLS[1]: [80_000, 25_000]},
    index=["TotalRevenue", "NetIncome"])   # sin Gross Profit ni Operating Income

# --- Fixture 3: patrimonio negativo --------------------------------------
BALANCE_NEG = pd.DataFrame(
    {COLS[0]: [100_000, -20_000, 60_000]},
    index=["Total Assets", "Stockholders Equity", "Total Debt"])

INFO_STD = {
    "longName": "Ejemplo S.A.", "city": "Austin", "state": "TX",
    "country": "United States", "sector": "Technology",
    "industry": "Semiconductors", "fullTimeEmployees": 12000,
    "currency": "USD", "financialCurrency": "USD",
    "marketCap": 1_200_000, "trailingPE": 24.5, "priceToBook": 6.1,
    "enterpriseToEbitda": 15.2, "trailingEps": 4.2,
}

INFO_ADR = {**INFO_STD, "longName": "Banco Ejemplo", "city": "Mumbai",
            "state": "", "country": "India",
            "currency": "USD", "financialCurrency": "INR"}

INFO_ETF = {"longName": "ETF Ejemplo", "currency": "USD",
            "totalAssets": 5_000_000, "yield": 0.013, "beta3Year": 1.02}


def check(nombre: str, cond: bool, detalle: str = "") -> bool:
    print(f"  {'OK  ' if cond else 'FALLA'} {nombre}" + (f"  -> {detalle}" if detalle and not cond else ""))
    return cond


def main() -> None:
    ok = True
    print("\n[1] Extraccion con etiquetas canonicas")
    k = F.extract_kpis("TEST", INFO_STD, INCOME_OK, BALANCE_OK, CASHFLOW_OK)
    ok &= check("revenue", k["revenue"] == 400_000, str(k["revenue"]))
    ok &= check("revenue_yoy ~ 14.3%", abs(k["revenue_yoy"] - (400_000/350_000 - 1)) < 1e-9)
    ok &= check("margen_bruto = 45%", abs(k["margen_bruto"] - 0.45) < 1e-9)
    ok &= check("margen_operativo = 30%", abs(k["margen_operativo"] - 0.30) < 1e-9)
    ok &= check("margen_neto = 23.75%", abs(k["margen_neto"] - 0.2375) < 1e-9)
    ok &= check("roe = 47.5%", abs(k["roe"] - 95_000/200_000) < 1e-9)
    ok &= check("roa = 19%", abs(k["roa"] - 95_000/500_000) < 1e-9)
    ok &= check("deuda/patrimonio = 0.45", abs(k["deuda_patrimonio"] - 0.45) < 1e-9)
    ok &= check("conversion_fcf", abs(k["conversion_fcf"] - 85_000/95_000) < 1e-9)
    ok &= check("periodo fiscal", k["periodo_fiscal"] == "2025-12-31", k["periodo_fiscal"])

    print("\n[2] Etiquetas alternativas y lineas ausentes")
    k2 = F.extract_kpis("BANK", INFO_STD, INCOME_ALT, BALANCE_OK, None)
    ok &= check("resuelve 'TotalRevenue' pegado", k2["revenue"] == 90_000, str(k2["revenue"]))
    ok &= check("resuelve 'NetIncome' pegado", k2["net_income"] == 30_000)
    ok &= check("margen_bruto es NaN sin Gross Profit", pd.isna(k2["margen_bruto"]))
    ok &= check("margen_neto igual se calcula", abs(k2["margen_neto"] - 1/3) < 1e-9)
    ok &= check("fcf NaN sin cashflow", pd.isna(k2["free_cash_flow"]))

    print("\n[3] Patrimonio negativo")
    k3 = F.extract_kpis("NEG", INFO_STD, INCOME_OK, BALANCE_NEG, None)
    ok &= check("roe negativo, no excepcion", k3["roe"] < 0, str(k3["roe"]))

    print("\n[4] Division por cero")
    ok &= check("_safe_div(1, 0) -> NaN", pd.isna(F._safe_div(1.0, 0.0)))
    ok &= check("_safe_div(1, NaN) -> NaN", pd.isna(F._safe_div(1.0, np.nan)))

    print("\n[5] Estados vacios o ausentes")
    k5 = F.extract_kpis("VACIO", {}, None, None, None)
    ok &= check("no explota con todo None", pd.isna(k5["revenue"]))
    ok &= check("_pick sobre DataFrame vacio", pd.isna(F._pick(pd.DataFrame(), F.REVENUE)))

    print("\n[6] Perfil y moneda de reporte de un ADR")
    p = F.extract_profile("IBN", INFO_ADR)
    ok &= check("HQ armado sin campos vacios", p["hq"] == "Mumbai, India", p["hq"])
    ok &= check("moneda cotizacion USD", p["moneda_cotizacion"] == "USD")
    ok &= check("moneda reporte INR", p["moneda_reporte"] == "INR")
    p2 = F.extract_profile("TEST", INFO_STD)
    ok &= check("HQ con estado", p2["hq"] == "Austin, TX, United States", p2["hq"])

    print("\n[7] Calendario de balances")
    class CalDict:
        calendar = {"Earnings Date": [pd.Timestamp("2026-10-28"),
                                      pd.Timestamp("2026-11-02")],
                    "Earnings Average": 1.35}
    c = F.extract_calendar("TEST", CalDict())
    ok &= check("toma la fecha mas cercana", c["proximo_balance"] == pd.Timestamp("2026-10-28"))
    ok &= check("rango => no confirmado", c["balance_confirmado"] is False)

    class CalOne:
        calendar = {"Earnings Date": [pd.Timestamp("2026-10-28")]}
    c2 = F.extract_calendar("TEST", CalOne())
    ok &= check("fecha unica => confirmado", c2["balance_confirmado"] is True)

    class CalBroken:
        @property
        def calendar(self):
            raise RuntimeError("api caida")
    c3 = F.extract_calendar("TEST", CalBroken())
    ok &= check("tolera fallo de la API", pd.isna(c3["proximo_balance"]))

    print("\n" + ("TODAS LAS VALIDACIONES PASARON" if ok else "HAY FALLOS"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
