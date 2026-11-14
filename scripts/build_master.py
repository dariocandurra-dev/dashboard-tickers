"""
Genera config/tickers_master.csv a partir de la hoja 'Tickers' del Excel original,
aplicando las correcciones de mapeo detectadas en el diagnostico de Etapa 1.

Cada fila define:
  ticker        -> ID canonico interno (el que usa todo el pipeline)
  sheet         -> hoja del Excel de la que sale el historico (o vacio si no hay)
  yf_symbol     -> simbolo para yfinance (fuente de actualizacion / reposicion)
  venue         -> plaza efectiva de la serie
  currency      -> moneda de cotizacion
  status        -> ok | empty | stale | mismapped
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_XLSX = Path("/mnt/user-data/uploads/Tickers.xlsx")

# --- Correcciones y mapeo a yfinance -------------------------------------
# Regla general: ticker US -> mismo simbolo. Argentinas -> se privilegia el ADR
# en USD para mantener comparabilidad en base 100 con el resto del panel.
# Cuando no existe ADR, se usa el local .BA (ARS) y queda marcado en 'currency'.

OVERRIDES = {
    # ticker : (sheet, yf_symbol, venue, currency, status, nota)
    "CAT":   ("",       "CAT",     "NYSE",   "USD", "empty",     "Hoja vacia: reponer full historico via API"),
    "DIA":   ("",       "DIA",     "NYSEArca","USD","empty",     "Hoja vacia: reponer full historico via API"),
    "EEM":   ("",       "EEM",     "NYSEArca","USD","empty",     "Hoja vacia: reponer full historico via API"),
    "SHOP":  ("",       "SHOP",    "NYSE",   "USD", "empty",     "Hoja vacia: reponer full historico via API"),
    "ALUA":  ("",       "ALUA.BA", "BYMA",   "ARS", "empty",     "Sin ADR: serie local en ARS"),
    "CRES":  ("",       "CRESY",   "NASDAQ", "USD", "empty",     "ADR Cresud (CRESY)"),
    "PAMP":  ("",       "PAM",     "NYSE",   "USD", "empty",     "ADR Pampa Energia (PAM)"),
    "TGSU2": ("",       "TGS",     "NYSE",   "USD", "empty",     "ADR TGS"),
    "YPFD":  ("",       "YPF",     "NYSE",   "USD", "empty",     "ADR YPF"),
    # --- mapeos rotos ---
    "VISTA": ("",       "VIST",    "NYSE",   "USD", "mismapped", "La hoja VISTA traia VGZ (Vista Gold). Descartada: refetch VIST"),
    "AUSO":  ("",       "AUSO.BA", "BYMA",   "ARS", "mismapped", "La hoja AUSO traia ASML. Sin ADR: serie local en ARS"),
    "ASML":  ("AUSO",   "ASML",    "NASDAQ", "USD", "mismapped", "Historico presente en hoja 'AUSO' (XAMS, EUR). Refetch ADR USD"),
    "HAVN":  ("",       "HAVA.BA", "BYMA",   "ARS", "mismapped", "La hoja HAVN traia Havn Life (CSE, corta 2023). Refetch Havanna"),
    # --- series validas pero desactualizadas / plaza distinta ---
    "TECO2": ("TECO2",  "TEO",     "NYSE",   "USD", "stale",     "Corta 2025-07-25. Plaza de origen sin identificar en el Excel"),
    "MDLZ":  ("MDLZ",   "MDLZ",    "NASDAQ", "USD", "stale",     "Corta 2026-01-12 (fuente XSGO)"),
    # Se sigue la plaza LOCAL, no el ADR: es la cotizacion que se venia mirando
    # y ademas mantiene continuidad con los 6,6 anos de historico del Excel,
    # que salen de NSE y XETR. El costo es que estas dos series no son
    # comparables en precio absoluto con el resto del panel (que esta en USD);
    # en base 100 si lo son, porque el rebase neutraliza la moneda.
    "INFY":  ("INFY",   "INFY.NS", "NSE",    "INR", "ok", "Plaza local NSE, en rupias"),
    "SAP":   ("SAP",    "SAP.DE",  "XETR",   "EUR", "ok", "Plaza local Frankfurt, en euros"),
}

# Series argentinas cuyo historico YA viene del ADR en USD (consistente, no tocar)
ETFS = {"SPY", "QQQ", "DIA", "IWM", "EEM", "EWZ", "XLE", "XLF",
        "ARKK", "GLD", "SMH", "XLV"}

ADR_OK = {
    "GGAL": "GGAL", "BMA": "BMA", "CEPU": "CEPU", "EDN": "EDN",
    "LOMA": "LOMA", "IRSA": "IRS",
}


def main():
    t = pd.read_excel(SRC_XLSX, "Tickers")
    t.columns = ["n", "ticker", "empresa", "mercado_origen", "sector", "pais"]
    sheets = set(pd.ExcelFile(SRC_XLSX).sheet_names)

    rows = []
    for _, r in t.iterrows():
        tk = str(r["ticker"]).strip()
        if tk in OVERRIDES:
            sheet, yf, venue, cur, status, nota = OVERRIDES[tk]
        else:
            sheet = tk if tk in sheets else ""
            yf = ADR_OK.get(tk, tk)
            venue = str(r["mercado_origen"]).strip()
            cur = "USD"
            status = "ok" if sheet else "empty"
            nota = ""
        rows.append({
            "ticker": tk,
            "empresa": r["empresa"],
            "sector": r["sector"],
            "pais": r["pais"],
            "mercado_origen": r["mercado_origen"],
            "sheet": sheet,
            "yf_symbol": yf,
            "venue": venue,
            "currency": cur,
            "asset_type": "ETF" if tk in ETFS else "EQUITY",
            "status": status,
            "nota": nota,
        })

    # --- Tickers adicionales (config/tickers_extra.csv) ---------------------
    # Archivo editable: se le agregan o sacan filas con Excel y el panel se
    # amplia solo. Las series se descargan en la proxima corrida de
    # repair_missing.py, porque no vienen en el Excel historico original.
    extra_path = ROOT / "config" / "tickers_extra.csv"
    if extra_path.exists():
        ex = pd.read_csv(extra_path)
        ya = {r["ticker"] for r in rows}
        for _, e in ex.iterrows():
            tk = str(e["ticker"]).strip()
            if not tk or tk in ya:
                continue
            rows.append({
                "ticker": tk, "empresa": e.get("empresa", ""),
                "sector": e.get("sector", ""), "pais": e.get("pais", ""),
                "mercado_origen": e.get("pais", ""), "sheet": "",
                "yf_symbol": e.get("yf_symbol", tk), "venue": "",
                "currency": "USD",
                "asset_type": e.get("asset_type", "EQUITY"),
                "status": "empty",
                "nota": e.get("nota", "") if pd.notna(e.get("nota")) else "",
            })

    m = pd.DataFrame(rows)

    # --- Taxonomia (config/clasificacion.csv) -------------------------------
    # Sobreescribe sector y agrega grupo e industria. Se hace aca y no en el
    # dashboard para que la clasificacion sea unica en todo el sistema.
    clas_path = ROOT / "config" / "clasificacion.csv"
    if clas_path.exists():
        cl = pd.read_csv(clas_path)
        m = m.drop(columns=["sector"]).merge(cl, on="ticker", how="left")
        m["grupo"] = m["grupo"].fillna("Sin clasificar")
        m["sector"] = m["sector"].fillna("Sin clasificar")
        m["industria"] = m["industria"].fillna("")

    out = ROOT / "config" / "tickers_master.csv"
    m.to_csv(out, index=False, encoding="utf-8")
    print(f"[OK] {out}  ({len(m)} tickers)")
    print(m["status"].value_counts().to_string())


if __name__ == "__main__":
    main()
