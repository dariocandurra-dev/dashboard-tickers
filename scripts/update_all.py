"""
ETAPA 4 - Orquestador de actualizacion diaria.

Encadena las tres capas y dispara las alertas:

    precios (incremental) -> indicadores -> fundamentales (si vencieron) -> alertas

Pensado para correr desatendido por cron o GitHub Actions. Cada paso se aisla:
si la descarga de fundamentales falla, los precios y las alertas tecnicas igual
se procesan. Un dashboard con fundamentales de ayer sirve; uno que no actualizo
nada porque un endpoint devolvio 500, no.

Uso:
    python scripts/update_all.py
    python scripts/update_all.py --sin-fundamentales
    python scripts/update_all.py --canal webhook --webhook-url https://...
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config as C
from src import alerts, indicators, signals

LOG_PATH = C.DATA_DIR / "update.log"
ESTADO_ALERTAS = C.DATA_DIR / "alertas_estado.parquet"
ALERTAS_DIR = C.DATA_DIR / "alertas"


def setup_log() -> logging.Logger:
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("update")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s",
                            "%Y-%m-%d %H:%M:%S")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_PATH)):
        h.setFormatter(fmt)
        log.addHandler(h)
    return log


def paso(log: logging.Logger, nombre: str, fn, *args, **kwargs):
    """Ejecuta un paso aislando su fallo del resto de la cadena."""
    log.info(f"--- {nombre} ---")
    try:
        out = fn(*args, **kwargs)
        log.info(f"{nombre}: OK")
        return out
    except Exception as exc:
        log.error(f"{nombre}: FALLO -> {exc}")
        log.debug(traceback.format_exc())
        return None


def actualizar_precios(log) -> pd.DataFrame:
    from src import api_loader
    master = C.load_master()
    existente = pd.read_parquet(C.PRICES_LONG)

    nuevos = api_loader.fetch_incremental(master, existente)
    if nuevos.empty:
        log.info("Sin ruedas nuevas")
        return existente

    combinado = pd.concat([existente, nuevos], ignore_index=True)
    combinado = (combinado.sort_values(["ticker", "date"])
                 .drop_duplicates(["ticker", "date"], keep="last"))
    combinado.to_parquet(C.PRICES_LONG, index=False)

    from src import normalize
    wide = normalize.to_wide(combinado)
    wide.to_parquet(C.PRICES_WIDE)
    normalize.base_100(wide, start=C.START_DATE).to_parquet(C.BASE100)

    log.info(f"{len(nuevos):,} observaciones nuevas en "
             f"{nuevos['ticker'].nunique()} series")
    return combinado


def recalcular_indicadores(log) -> None:
    long = pd.read_parquet(C.PRICES_LONG)
    ind = indicators.compute_panel(long)
    sig = signals.detect_panel(ind)
    ind.to_parquet(C.DATA_DIR / "indicators.parquet", index=False)
    sig.to_parquet(C.DATA_DIR / "signals.parquet", index=False)

    snap = signals.snapshot(ind, sig, C.load_master())
    snap.to_csv(C.DATA_DIR / "snapshot_tecnico.csv", index=False)
    log.info(f"Indicadores recalculados sobre {ind['ticker'].nunique()} series")


def actualizar_fundamentales(log) -> None:
    import subprocess
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "stage3_fundamentals.py")],
        capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-400:])
    log.info("Fundamentales actualizados")


def procesar_alertas(log, notificador) -> pd.DataFrame:
    master = C.load_master()
    sig = pd.read_parquet(C.DATA_DIR / "signals.parquet")
    snap_path = C.DATA_DIR / "snapshot_tecnico.csv"
    snap = pd.read_csv(snap_path) if snap_path.exists() else None

    cal_path = C.DATA_DIR / "earnings_calendar.parquet"
    cal = pd.read_parquet(cal_path) if cal_path.exists() else None

    bloques = [
        alerts.alertas_tecnicas(sig, master),
        alerts.alertas_balance(cal, master, dias=alerts.DIAS_AVISO_BALANCE),
        alerts.alertas_rsi(snap, master),
    ]
    todas = pd.concat([b for b in bloques if not b.empty], ignore_index=True) \
        if any(not b.empty for b in bloques) else alerts._vacio()

    nuevas = alerts.filtrar_nuevas(todas, ESTADO_ALERTAS)
    log.info(f"{len(todas)} alertas vigentes | {len(nuevas)} nuevas")

    if not nuevas.empty:
        if notificador.enviar(nuevas):
            alerts.registrar(nuevas, ESTADO_ALERTAS)
        else:
            log.warning("Envio fallido: no se marcan como notificadas")
    return nuevas


def regenerar_html(log) -> None:
    """Reescribe el HTML autocontenido con los datos recien actualizados."""
    import build_html
    build_html.main()
    log.info(f"HTML regenerado: {build_html.SALIDA.name}")


def build_notificador(canal: str, webhook_url: str | None):
    if canal == "webhook":
        url = webhook_url or os.getenv("ALERT_WEBHOOK_URL")
        if not url:
            raise SystemExit("Falta la URL del webhook (--webhook-url o ALERT_WEBHOOK_URL)")
        return alerts.Webhook(url)
    if canal == "email":
        faltan = [v for v in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "ALERT_TO")
                  if not os.getenv(v)]
        if faltan:
            raise SystemExit(f"Faltan variables de entorno: {', '.join(faltan)}")
        return alerts.Email(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587")),
                            os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"),
                            os.getenv("ALERT_TO"))
    return alerts.ConsolaJSON(ALERTAS_DIR)


def main(sin_fundamentales: bool = False, sin_precios: bool = False,
         canal: str = "consola", webhook_url: str | None = None) -> None:
    log = setup_log()
    log.info("=" * 58)
    log.info("Actualizacion del panel")

    if not sin_precios:
        paso(log, "Precios", actualizar_precios, log)
    paso(log, "Indicadores", recalcular_indicadores, log)
    if not sin_fundamentales:
        paso(log, "Fundamentales", actualizar_fundamentales, log)

    notificador = build_notificador(canal, webhook_url)
    paso(log, "Alertas", procesar_alertas, log, notificador)
    paso(log, "Dashboard HTML", regenerar_html, log)
    log.info("Fin")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sin-fundamentales", action="store_true")
    p.add_argument("--sin-precios", action="store_true")
    p.add_argument("--canal", choices=["consola", "webhook", "email"],
                   default="consola")
    p.add_argument("--webhook-url", default=None)
    a = p.parse_args()
    main(a.sin_fundamentales, a.sin_precios, a.canal, a.webhook_url)
