"""
ETAPA 3 - Descarga de fundamentales y construccion de las fichas.

Los fundamentales cambian con cada balance, no con cada rueda: bajarlos todos
los dias es desperdiciar cuota de API para reescribir los mismos numeros. El
script mantiene un cache con vencimiento y solo refresca lo vencido.

Uso:
    python scripts/stage3_fundamentals.py              # respeta el cache
    python scripts/stage3_fundamentals.py --force      # refresca todo
    python scripts/stage3_fundamentals.py --only AAPL,MSFT
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config as C
from src import fundamentals as F
from src import ficha as FICHA

PERFILES = C.DATA_DIR / "perfiles.parquet"
KPIS = C.DATA_DIR / "kpis.parquet"
CALENDARIO = C.DATA_DIR / "earnings_calendar.parquet"
ERRORES = C.DATA_DIR / "fundamentales_errores.csv"
COBERTURA = C.DATA_DIR / "cobertura_fundamental.csv"

# Vencimiento del cache: los estados contables se actualizan por trimestre,
# el calendario de balances conviene refrescarlo mas seguido.
TTL_KPIS_DIAS = 7
TTL_CALENDARIO_DIAS = 1


def _vencidos(path: Path, ttl_dias: int, tickers: set[str]) -> set[str]:
    """Tickers sin dato en cache o con dato mas viejo que el TTL."""
    if not path.exists():
        return set(tickers)
    try:
        df = pd.read_parquet(path)
    except Exception:
        return set(tickers)
    if "fetched_at" not in df.columns:
        return set(tickers)

    corte = pd.Timestamp.now() - pd.Timedelta(days=ttl_dias)
    frescos = set(df.loc[pd.to_datetime(df["fetched_at"]) >= corte, "ticker"])
    return set(tickers) - frescos


def _merge_cache(path: Path, nuevo: pd.DataFrame) -> pd.DataFrame:
    """Combina lo recien bajado con el cache previo, priorizando lo nuevo."""
    if nuevo.empty:
        return pd.read_parquet(path) if path.exists() else nuevo
    nuevo = nuevo.copy()
    nuevo["fetched_at"] = pd.Timestamp.now()
    if path.exists():
        try:
            viejo = pd.read_parquet(path)
            viejo = viejo[~viejo["ticker"].isin(nuevo["ticker"])]
            nuevo = pd.concat([viejo, nuevo], ignore_index=True)
        except Exception:
            pass
    return nuevo.sort_values("ticker").reset_index(drop=True)


def main(force: bool = False, only: str | None = None) -> None:
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    master = C.load_master()

    if only:
        pedidos = {t.strip().upper() for t in only.split(",")}
        master = master[master["ticker"].isin(pedidos)]

    todos = set(master["ticker"])
    pendientes = todos if force else _vencidos(KPIS, TTL_KPIS_DIAS, todos)
    print(f"[1/3] {len(todos)} tickers | a descargar: {len(pendientes)}")

    if pendientes:
        rows = [(r["ticker"], r["yf_symbol"], r["asset_type"] == "ETF")
                for _, r in master.iterrows() if r["ticker"] in pendientes]
        res = F.fetch_many(rows)
        print(f"[2/3] Descargados {len(res['perfiles'])} perfiles, "
              f"{len(res['errores'])} fallos")

        _merge_cache(PERFILES, res["perfiles"]).to_parquet(PERFILES, index=False)
        _merge_cache(KPIS, res["kpis"]).to_parquet(KPIS, index=False)
        _merge_cache(CALENDARIO, res["calendario"]).to_parquet(CALENDARIO, index=False)
        if not res["errores"].empty:
            res["errores"].to_csv(ERRORES, index=False)
    else:
        print("[2/3] Todo fresco en cache, no se descarga nada")

    reporte_cobertura(master)
    armar_fichas(C.load_master())
    print(f"[3/3] Persistido en {C.DATA_DIR}")


def _leer(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def armar_fichas(master: pd.DataFrame) -> None:
    """Consolida perfil + KPIs + calendario + tecnico en una fila por ticker."""
    snap_path = C.DATA_DIR / "snapshot_tecnico.csv"
    snap = pd.read_csv(snap_path) if snap_path.exists() else None

    f = FICHA.build(master, _leer(PERFILES), _leer(KPIS), _leer(CALENDARIO), snap)
    f.to_parquet(C.DATA_DIR / "fichas.parquet", index=False)
    f.to_csv(C.DATA_DIR / "fichas.csv", index=False)

    huecos = FICHA.gaps(f)
    if not huecos.empty:
        huecos.to_csv(C.DATA_DIR / "fichas_incompletas.csv", index=False)
    print(f"\n      Fichas armadas: {len(f)} | incompletas: {len(huecos)}")


def reporte_cobertura(master: pd.DataFrame) -> None:
    """Mide que porcentaje de cada KPI quedo efectivamente poblado."""
    if not KPIS.exists():
        print("      Sin KPIs para reportar")
        return

    k = pd.read_parquet(KPIS)
    eq = k[~k.get("es_etf", pd.Series(False, index=k.index)).fillna(False)]
    campos = ["revenue", "net_income", "margen_bruto", "margen_operativo",
              "margen_neto", "roe", "roa", "deuda_patrimonio", "free_cash_flow",
              "market_cap", "pe_trailing", "ev_ebitda"]

    filas = []
    for c in campos:
        if c not in eq.columns:
            filas.append({"kpi": c, "con_dato": 0, "total": len(eq), "cobertura": 0.0})
            continue
        n = int(eq[c].notna().sum())
        filas.append({"kpi": c, "con_dato": n, "total": len(eq),
                      "cobertura": round(n / max(len(eq), 1), 3)})

    cob = pd.DataFrame(filas)
    cob.to_csv(COBERTURA, index=False)
    print("\n      Cobertura por KPI (solo acciones):")
    for _, r in cob.iterrows():
        print(f"        {r['kpi']:<20} {r['con_dato']:>3}/{r['total']:<3} "
              f"({r['cobertura']:.0%})")

    if "moneda_reporte" in eq.columns:
        mult = eq[eq["moneda_reporte"].fillna("") != "USD"]
        if len(mult):
            print(f"\n      Reportan en moneda distinta de USD: {len(mult)}")
            for _, r in mult.iterrows():
                print(f"        {r['ticker']:<6} {r['moneda_reporte']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    p.add_argument("--only", type=str, default=None)
    main(**vars(p.parse_args()))
