"""
Genera config/clasificacion.csv: la taxonomia del panel.

Criterio (alineado con GICS, que es el esquema que usan los heatmaps sectoriales
tipo TradingView):

  GRUPO  -> como se agrupa en el dashboard.
            "Argentina" para todo papel argentino, sin importar su sector.
            "Índices"   para ETFs e indices.
            El sector GICS para el resto.

  SECTOR -> el sector economico, que SIEMPRE se asigna, incluso a las argentinas
            y a los ETFs. Eso es lo que permite la doble pertenencia: GGAL vive
            en el grupo Argentina pero sigue siendo Financiero, y XLF vive en
            Índices pero representa al sector Financiero.

Los 11 sectores GICS resuelven el problema de fondo que tenia la clasificacion
original: "Bancos", "Finanzas", "Pagos" y "Tecnología financiera" eran cuatro
cajones para lo que es un unico sector. BAC y C ahora caen en el mismo lugar.

Nota sobre V, MA y PYPL: desde la reclasificacion GICS de marzo de 2023 los
procesadores de pago dejaron de ser Tecnologia y pasaron a Financiero.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ROOT = Path(__file__).resolve().parents[1]

TEC = "Tecnología"
COM = "Servicios de Comunicación"
CDI = "Consumo Discrecional"
CBA = "Consumo Básico"
FIN = "Financiero"
SAL = "Salud"
IND = "Industrial"
ENE = "Energía"
MAT = "Materiales"
UTI = "Servicios Públicos"
INM = "Inmobiliario"

# ticker -> (sector, industria)
ACCIONES = {
    # --- Tecnología ---
    "AAPL": (TEC, "Hardware"), "MSFT": (TEC, "Software"),
    "NVDA": (TEC, "Semiconductores"), "AVGO": (TEC, "Semiconductores"),
    "AMD": (TEC, "Semiconductores"), "QCOM": (TEC, "Semiconductores"),
    "INTC": (TEC, "Semiconductores"), "ADI": (TEC, "Semiconductores"),
    "MU": (TEC, "Semiconductores"), "TSM": (TEC, "Semiconductores"),
    "ASML": (TEC, "Equipamiento de semiconductores"),
    "ORCL": (TEC, "Software"), "CRM": (TEC, "Software"),
    "ADBE": (TEC, "Software"), "IBM": (TEC, "Servicios de TI"),
    "CSCO": (TEC, "Equipamiento de red"), "DDOG": (TEC, "Software"),
    "TEAM": (TEC, "Software"), "PLTR": (TEC, "Software"),
    "INFY": (TEC, "Servicios de TI"), "SAP": (TEC, "Software"),
    "SHOP": (TEC, "Software"), "ZM": (TEC, "Software"),
    "MSTR": (TEC, "Software y tesorería en bitcoin"),
    # --- Servicios de Comunicación ---
    "GOOGL": (COM, "Medios interactivos"), "META": (COM, "Medios interactivos"),
    "SNAP": (COM, "Medios interactivos"), "BIDU": (COM, "Medios interactivos"),
    "DIS": (COM, "Entretenimiento"), "NFLX": (COM, "Entretenimiento"),
    "T": (COM, "Telecomunicaciones"), "VZ": (COM, "Telecomunicaciones"),
    # --- Consumo Discrecional ---
    "AMZN": (CDI, "Comercio electrónico"), "BABA": (CDI, "Comercio electrónico"),
    "TSLA": (CDI, "Automotrices"), "TM": (CDI, "Automotrices"),
    "RACE": (CDI, "Automotrices de lujo"), "HD": (CDI, "Retail especializado"),
    "NKE": (CDI, "Indumentaria"), "MCD": (CDI, "Restaurantes"),
    "SBUX": (CDI, "Restaurantes"),
    # --- Consumo Básico ---
    "KO": (CBA, "Bebidas"), "PEP": (CBA, "Bebidas y snacks"),
    "ABEV": (CBA, "Bebidas"), "PG": (CBA, "Cuidado personal"),
    "UL": (CBA, "Cuidado personal"), "MDLZ": (CBA, "Alimentos"),
    "MO": (CBA, "Tabaco"), "WMT": (CBA, "Retail de consumo masivo"),
    "COST": (CBA, "Retail de consumo masivo"),
    # --- Financiero ---
    "JPM": (FIN, "Bancos"), "BAC": (FIN, "Bancos"), "C": (FIN, "Bancos"),
    "GS": (FIN, "Banca de inversión"), "HSBC": (FIN, "Bancos"),
    "RY": (FIN, "Bancos"), "IBN": (FIN, "Bancos"), "ITUB": (FIN, "Bancos"),
    "NU": (FIN, "Banca digital"), "BRK-B": (FIN, "Holding y seguros"),
    "V": (FIN, "Procesadores de pago"), "MA": (FIN, "Procesadores de pago"),
    "AXP": (FIN, "Tarjetas de crédito"), "PYPL": (FIN, "Procesadores de pago"),
    # --- Salud ---
    "JNJ": (SAL, "Farmacéuticas"), "PFE": (SAL, "Farmacéuticas"),
    "LLY": (SAL, "Farmacéuticas"), "NVO": (SAL, "Farmacéuticas"),
    "UNH": (SAL, "Seguros de salud"), "ISRG": (SAL, "Equipamiento médico"),
    # --- Industrial ---
    "BA": (IND, "Aeroespacial y defensa"), "SPCX": (IND, "Aeroespacial"),
    "AXON": (IND, "Aeroespacial y defensa"), "CAT": (IND, "Maquinaria"),
    "GE": (IND, "Conglomerado industrial"), "MMM": (IND, "Conglomerado industrial"),
    "FDX": (IND, "Logística"), "UPS": (IND, "Logística"),
    # --- Energía ---
    "XOM": (ENE, "Petróleo integrado"), "CVX": (ENE, "Petróleo integrado"),
    "PBR": (ENE, "Petróleo integrado"),
    # --- Servicios Públicos ---
    "DUK": (UTI, "Electricidad"), "NEE": (UTI, "Electricidad"),
    "SO": (UTI, "Electricidad"),
    # --- Materiales ---
    "DOW": (MAT, "Químicos"), "VALE": (MAT, "Minería"),
}

# Argentinas: grupo aparte, pero con sector asignado igual
ARGENTINAS = {
    "GGAL": (FIN, "Bancos"), "BMA": (FIN, "Bancos"),
    "YPFD": (ENE, "Petróleo integrado"), "VISTA": (ENE, "Exploración y producción"),
    "PAMP": (ENE, "Energía integrada"), "TGSU2": (ENE, "Transporte de gas"),
    "CEPU": (UTI, "Generación eléctrica"), "EDN": (UTI, "Distribución eléctrica"),
    "ALUA": (MAT, "Aluminio"), "LOMA": (MAT, "Cemento"),
    "CRES": (CBA, "Agropecuaria"), "IRSA": (INM, "Real estate"),
    "AUSO": (IND, "Concesiones viales"), "TECO2": (COM, "Telecomunicaciones"),
    "MELI": (CDI, "Comercio electrónico"), "GLOB": (TEC, "Servicios de TI"),
    "HAVN": (CDI, "Alimentos y cafeterías"),
}

# ETFs e indices: grupo "Índices", con el sector que representan
FONDOS = {
    "SPY": ("Mercado amplio", "S&P 500"), "QQQ": ("Mercado amplio", "Nasdaq 100"),
    "DIA": ("Mercado amplio", "Dow Jones"), "IWM": ("Mercado amplio", "Small caps"),
    "EEM": ("Regional", "Emergentes"), "EWZ": ("Regional", "Brasil"),
    "EWY": ("Regional", "Corea"), "ARGT": ("Regional", "Argentina"),
    "XLK": (TEC, "Sector tecnología"), "SMH": (TEC, "Semiconductores"),
    "ARKK": (TEC, "Innovación disruptiva"),
    "XLF": (FIN, "Sector financiero"), "XLV": (SAL, "Sector salud"),
    "XLE": (ENE, "Sector energía"), "XLY": (CDI, "Sector consumo discrecional"),
    "XLP": (CBA, "Sector consumo básico"), "XLI": (IND, "Sector industrial"),
    "XLU": (UTI, "Sector servicios públicos"), "XLB": (MAT, "Sector materiales"),
    "XLRE": (INM, "Sector inmobiliario"), "XLC": (COM, "Sector comunicaciones"),
    "GLD": (MAT, "Oro"),
    "TLT": ("Renta fija", "Tesoros a 20+ años"),
    "HYG": ("Renta fija", "Alto rendimiento corporativo"),
    "UUP": ("Divisas", "Índice dólar"),
    "IBIT": ("Cripto", "Bitcoin"),
    "VIX": ("Volatilidad", "Índice de volatilidad CBOE"),
}


def main() -> None:
    filas = []
    for tk, (sec, ind) in ACCIONES.items():
        filas.append({"ticker": tk, "grupo": sec, "sector": sec, "industria": ind})
    for tk, (sec, ind) in ARGENTINAS.items():
        filas.append({"ticker": tk, "grupo": "Argentina", "sector": sec, "industria": ind})
    for tk, (sec, ind) in FONDOS.items():
        filas.append({"ticker": tk, "grupo": "Índices", "sector": sec, "industria": ind})

    df = pd.DataFrame(filas).sort_values(["grupo", "sector", "ticker"])
    out = ROOT / "config" / "clasificacion.csv"
    df.to_csv(out, index=False, encoding="utf-8")

    print(f"[OK] {out}  ({len(df)} tickers)")
    print("\nPor grupo:")
    print(df["grupo"].value_counts().to_string())


if __name__ == "__main__":
    main()
