"""
Genera un dashboard HTML autocontenido: un unico archivo que se abre con doble
clic, sin servidor, sin Python corriendo, sin conexion a internet.

Todos los datos van embebidos como JSON dentro del archivo y los graficos se
dibujan en SVG con JavaScript sin dependencias externas. Eso lo hace portable:
se manda por mail, se sube a una carpeta compartida o se abre desde un pendrive
y funciona igual.

Para que el archivo no se vuelva inmanejable, las series historicas se compactan:
  - un indice de fechas global, y arrays alineados por posicion (no se repite la
    fecha en cada punto de cada serie)
  - valores redondeados a la precision que efectivamente se muestra
  - el histograma del MACD no se guarda: se calcula en el navegador como la
    diferencia entre la linea y su senal

Uso:  python scripts/build_html.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config as C
from src import alerts as A

SALIDA = C.ROOT / "Dashboard_Tickers.html"


def _r(serie: pd.Series, dec: int) -> list:
    """Redondea y convierte a lista con None en lugar de NaN (JSON no tiene NaN)."""
    return [None if pd.isna(v) else round(float(v), dec) for v in serie]


def construir_payload() -> dict:
    master = C.load_master()
    ind = pd.read_parquet(C.DATA_DIR / "indicators.parquet")
    sig = pd.read_parquet(C.DATA_DIR / "signals.parquet")
    snap = pd.read_csv(C.DATA_DIR / "snapshot_tecnico.csv")
    snap["date"] = pd.to_datetime(snap["date"])

    fichas = pd.read_parquet(C.DATA_DIR / "fichas.parquet") \
        if (C.DATA_DIR / "fichas.parquet").exists() else None
    cal_path = C.DATA_DIR / "earnings_calendar.parquet"
    cal = pd.read_parquet(cal_path) if cal_path.exists() else None

    # --- Indice de fechas global -----------------------------------------
    fechas = pd.DatetimeIndex(sorted(ind["date"].unique()))
    pos = {d: i for i, d in enumerate(fechas)}

    # --- Series por ticker: SOLO los cierres -----------------------------
    # Las medias, el MACD y el RSI se derivan todos del cierre, asi que
    # mandarlos precalculados es guardar seis columnas donde alcanza con una.
    # El navegador los recalcula al abrir la ficha, con el mismo codigo que
    # usa Python (validado al 1e-14).
    #
    # Formato: i0 = posicion de la primera rueda en el indice global,
    #          c  = cierres densos, sin huecos,
    #          g  = posiciones (relativas a i0) en las que este papel NO opero.
    # Guardar los huecos como excepcion y no la serie llena de nulos importa:
    # el calendario global es la union de plazas con feriados distintos, asi
    # que una serie tipica trae ~70 nulos sobre 1732 ruedas.
    series = {}
    for tk, g in ind.groupby("ticker", sort=True):
        g = g.sort_values("date")
        idx = [pos[d] for d in g["date"]]
        i0, i1 = min(idx), max(idx)
        presentes = set(idx)
        huecos = [i - i0 for i in range(i0, i1 + 1) if i not in presentes]
        series[tk] = {
            "i0": int(i0),
            "c": _r(g["close"], 2),
            "g": huecos,
        }

    # --- Tabla del panel --------------------------------------------------
    meta_tk = master.set_index("ticker")
    monedas = meta_tk["currency"].to_dict()
    grupos = meta_tk["grupo"].to_dict()
    sectores = meta_tk["sector"].to_dict()
    industrias = meta_tk["industria"].fillna("").to_dict()
    tipos = meta_tk["asset_type"].to_dict()
    panel = []
    for _, r in snap.iterrows():
        panel.append({
            "t": r["ticker"], "e": r.get("empresa", ""),
            "cur": monedas.get(r["ticker"], "USD"),
            "g": grupos.get(r["ticker"], ""),
            "sec": sectores.get(r["ticker"], ""),
            "ind": industrias.get(r["ticker"], ""),
            "tipo": tipos.get(r["ticker"], "EQUITY"),
            "p": r.get("pais", ""),
            "c": None if pd.isna(r["close"]) else round(float(r["close"]), 2),
            "d200": None if pd.isna(r["dist_ma200"]) else round(float(r["dist_ma200"]), 4),
            "rsi": None if pd.isna(r["rsi14"]) else round(float(r["rsi14"]), 1),
            "mh": None if pd.isna(r.get("macd_hist")) else round(float(r["macd_hist"]), 3),
            "vol": None if pd.isna(r.get("vol20")) else round(float(r["vol20"]), 4),
            "dd": None if pd.isna(r.get("drawdown")) else round(float(r["drawdown"]), 4),
            "tend": r.get("tendencia_larga") if pd.notna(r.get("tendencia_larga")) else "",
            "ab": bool(r.get("above_ma200_conf")) if pd.notna(r.get("above_ma200_conf")) else None,
        })

    # --- Alertas ----------------------------------------------------------
    bloques = [A.alertas_tecnicas(sig, master),
               A.alertas_balance(cal, master, dias=A.DIAS_AVISO_BALANCE),
               A.alertas_rsi(snap, master)]
    vivos = [b for b in bloques if not b.empty]
    alertas = []
    if vivos:
        t = pd.concat(vivos, ignore_index=True)
        for _, r in t.iterrows():
            alertas.append({"t": r["ticker"], "e": r["empresa"],
                            "f": r["fecha_evento"].strftime("%Y-%m-%d"),
                            "sev": r["severidad"], "d": r["detalle"]})

    # --- Fichas fundamentales --------------------------------------------
    fund = {}
    if fichas is not None:
        campos = ["nombre", "hq", "industria", "empleados", "moneda_reporte",
                  "periodo_fiscal", "revenue", "revenue_yoy", "net_income",
                  "margen_bruto", "margen_operativo", "margen_neto", "roe", "roa",
                  "deuda_patrimonio", "market_cap", "pe_trailing", "ev_ebitda",
                  "dividend_yield", "proximo_balance"]
        for _, r in fichas.iterrows():
            d = {}
            for c in campos:
                v = r.get(c)
                if pd.isna(v):
                    continue
                d[c] = str(v)[:10] if c == "proximo_balance" else (
                    float(v) if isinstance(v, (int, float, np.floating)) else str(v))
            if d:
                fund[r["ticker"]] = d

    # --- Calendario -------------------------------------------------------
    calendario = []
    if cal is not None and not cal.empty:
        c = cal.copy()
        c["proximo_balance"] = pd.to_datetime(c["proximo_balance"], errors="coerce")
        c = c.dropna(subset=["proximo_balance"]).sort_values("proximo_balance")
        c = c.merge(master[["ticker", "empresa"]], on="ticker", how="left")
        hoy = pd.Timestamp.now().normalize()
        for _, r in c.iterrows():
            calendario.append({
                "t": r["ticker"], "e": r.get("empresa", ""),
            "cur": monedas.get(r["ticker"], "USD"),
                "f": r["proximo_balance"].strftime("%Y-%m-%d"),
                "dias": int((r["proximo_balance"] - hoy).days),
                "conf": bool(r.get("balance_confirmado", False))})

    pend = sorted(set(master["ticker"]) - set(ind["ticker"].unique()))

    return {
        "meta": {
            "corte": snap["date"].max().strftime("%Y-%m-%d"),
            "generado": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            "n_series": int(snap["ticker"].nunique()),
            "n_master": int(len(master)),
            "pendientes": pend,
            "con_fundamentales": len(fund),
        },
        "fechas": [d.strftime("%Y-%m-%d") for d in fechas],
        "series": series,
        "panel": panel,
        "alertas": alertas,
        "fund": fund,
        "calendario": calendario,
    }


def main() -> None:
    print("Construyendo payload...")
    data = construir_payload()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    print(f"  datos embebidos: {len(blob) / 1e6:.1f} MB")

    plantilla = (C.ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
    html = plantilla.replace("/*__DATOS__*/", blob)
    SALIDA.write_text(html, encoding="utf-8")

    mb = SALIDA.stat().st_size / 1e6
    print(f"\nListo: {SALIDA}  ({mb:.1f} MB)")
    print(f"  {data['meta']['n_series']} series | corte {data['meta']['corte']} "
          f"| {len(data['alertas'])} alertas")
    if data["meta"]["pendientes"]:
        print(f"  Sin datos: {', '.join(data['meta']['pendientes'])}")


if __name__ == "__main__":
    main()
