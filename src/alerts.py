"""
ETAPA 4 - Motor de alertas.

Dos familias de alertas:

  TECNICA    -> el precio perforo la MA200 (cruce confirmado, con histeresis)
  CALENDARIO -> el emisor presenta balance dentro de los proximos N dias

El problema central de un motor de alertas no es detectar: eso ya lo resolvio la
Etapa 2. Es *no repetir*. Una alerta que se reenvia todos los dias deja de
leerse en una semana, y a partir de ahi el sistema es ruido con costo de
mantenimiento. Por eso cada disparo se registra en un estado persistente y se
suprime mientras siga vigente la misma condicion.

La clave de deduplicacion incluye la fecha del evento, no la fecha de corrida:
si el cruce de NVDA fue el 12-ago, la alerta es la misma el 13 y el 14. Recien
un cruce nuevo genera un disparo nuevo.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

# Anticipacion del aviso de balance, en dias corridos
DIAS_AVISO_BALANCE = 7

SEVERIDAD = {
    "perforacion_ma200": "alta",
    "recuperacion_ma200": "media",
    "death_cross": "alta",
    "golden_cross": "media",
    "balance_proximo": "media",
    "rsi_extremo": "baja",
}


# --- Deteccion ------------------------------------------------------------

def alertas_tecnicas(sig: pd.DataFrame, master: pd.DataFrame,
                     ventana_ruedas: int = 3) -> pd.DataFrame:
    """Cruces confirmados ocurridos en las ultimas `ventana_ruedas` de cada serie.

    Se mira una ventana corta y no solo la ultima rueda porque las series tienen
    calendarios distintos: un feriado en BYMA no debe hacer perder el evento de
    un papel argentino cuando el resto del panel opero.
    """
    filas = []
    for tk, g in sig.groupby("ticker", sort=True):
        g = g.sort_values("date").tail(ventana_ruedas)
        for _, r in g.iterrows():
            if r.get("cross_down_ma200_conf"):
                filas.append((tk, r["date"], "perforacion_ma200",
                              "El precio cerro por debajo de la MA200"))
            elif r.get("cross_up_ma200_conf"):
                filas.append((tk, r["date"], "recuperacion_ma200",
                              "El precio recupero la MA200"))
            if r.get("death_cross"):
                filas.append((tk, r["date"], "death_cross",
                              "La MA50 cruzo por debajo de la MA200"))
            elif r.get("golden_cross"):
                filas.append((tk, r["date"], "golden_cross",
                              "La MA50 cruzo por encima de la MA200"))

    if not filas:
        return _vacio()

    df = pd.DataFrame(filas, columns=["ticker", "fecha_evento", "tipo", "detalle"])
    return _enriquecer(df, master)


def alertas_balance(calendario: pd.DataFrame, master: pd.DataFrame,
                    dias: int = DIAS_AVISO_BALANCE) -> pd.DataFrame:
    """Emisores que presentan balance dentro de los proximos `dias` corridos."""
    if calendario is None or calendario.empty:
        return _vacio()

    cal = calendario.copy()
    cal["proximo_balance"] = pd.to_datetime(cal["proximo_balance"], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    cal["dias_restantes"] = (cal["proximo_balance"] - hoy).dt.days

    prox = cal[(cal["dias_restantes"] >= 0) & (cal["dias_restantes"] <= dias)]
    if prox.empty:
        return _vacio()

    filas = []
    for _, r in prox.iterrows():
        confirmado = "confirmada" if r.get("balance_confirmado") else "estimada"
        d = int(r["dias_restantes"])
        cuando = "hoy" if d == 0 else ("manana" if d == 1 else f"en {d} dias")
        filas.append((r["ticker"], r["proximo_balance"], "balance_proximo",
                      f"Presenta balance {cuando} ({r['proximo_balance'].date()}, "
                      f"fecha {confirmado})"))

    df = pd.DataFrame(filas, columns=["ticker", "fecha_evento", "tipo", "detalle"])
    return _enriquecer(df, master)


def alertas_rsi(snapshot: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """RSI en zona extrema. Informativa: no dispara por si sola una decision."""
    if snapshot is None or snapshot.empty or "rsi_zona" not in snapshot.columns:
        return _vacio()

    ext = snapshot[snapshot["rsi_zona"].isin(["sobrecompra", "sobreventa"])]
    if ext.empty:
        return _vacio()

    filas = [(r["ticker"], pd.Timestamp(r["date"]), "rsi_extremo",
              f"RSI en {r['rsi_zona']} ({r['rsi14']:.0f})")
             for _, r in ext.iterrows()]
    df = pd.DataFrame(filas, columns=["ticker", "fecha_evento", "tipo", "detalle"])
    return _enriquecer(df, master)


def _vacio() -> pd.DataFrame:
    return pd.DataFrame(columns=["ticker", "empresa", "fecha_evento", "tipo",
                                 "severidad", "detalle", "clave"])


def _enriquecer(df: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """Agrega nombre, severidad y la clave de deduplicacion."""
    df = df.merge(master[["ticker", "empresa"]], on="ticker", how="left")
    df["severidad"] = df["tipo"].map(SEVERIDAD).fillna("baja")
    df["fecha_evento"] = pd.to_datetime(df["fecha_evento"])
    df["clave"] = (df["ticker"] + "|" + df["tipo"] + "|"
                   + df["fecha_evento"].dt.strftime("%Y-%m-%d"))
    return df[["ticker", "empresa", "fecha_evento", "tipo", "severidad",
               "detalle", "clave"]].sort_values(
        ["severidad", "fecha_evento"], ascending=[True, False])


# --- Deduplicacion --------------------------------------------------------

def filtrar_nuevas(alertas: pd.DataFrame, estado_path: Path) -> pd.DataFrame:
    """Descarta las alertas ya notificadas segun el estado persistido."""
    if alertas.empty:
        return alertas
    if not estado_path.exists():
        return alertas

    try:
        previas = set(pd.read_parquet(estado_path)["clave"])
    except Exception:
        return alertas
    return alertas[~alertas["clave"].isin(previas)]


def registrar(alertas: pd.DataFrame, estado_path: Path,
              retencion_dias: int = 120) -> None:
    """Persiste las claves notificadas y purga las mas viejas que la retencion."""
    if alertas.empty:
        return

    nuevo = alertas[["clave", "ticker", "tipo", "fecha_evento"]].copy()
    nuevo["notificada_at"] = pd.Timestamp.now()

    if estado_path.exists():
        try:
            viejo = pd.read_parquet(estado_path)
            nuevo = pd.concat([viejo, nuevo], ignore_index=True)
        except Exception:
            pass

    nuevo = nuevo.drop_duplicates("clave", keep="first")
    corte = pd.Timestamp.now() - pd.Timedelta(days=retencion_dias)
    nuevo = nuevo[pd.to_datetime(nuevo["notificada_at"]) >= corte]
    nuevo.to_parquet(estado_path, index=False)


# --- Notificacion ---------------------------------------------------------

def formatear(alertas: pd.DataFrame) -> str:
    """Texto plano legible, agrupado por severidad."""
    if alertas.empty:
        return "Sin alertas nuevas."

    orden = {"alta": 0, "media": 1, "baja": 2}
    lineas = [f"ALERTAS — {datetime.now():%Y-%m-%d %H:%M}", ""]
    for sev in sorted(alertas["severidad"].unique(), key=lambda s: orden.get(s, 9)):
        sub = alertas[alertas["severidad"] == sev]
        lineas.append(f"[{sev.upper()}] {len(sub)}")
        for _, r in sub.iterrows():
            lineas.append(f"  {r['ticker']:<6} {r['empresa'][:28]:<28} {r['detalle']}")
        lineas.append("")
    return "\n".join(lineas)


class Notificador:
    """Interfaz de salida. Las subclases solo implementan `enviar`."""

    def enviar(self, alertas: pd.DataFrame) -> bool:
        raise NotImplementedError


class ConsolaJSON(Notificador):
    """Default: imprime en consola y deja el detalle en un JSON por corrida."""

    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)

    def enviar(self, alertas: pd.DataFrame) -> bool:
        print(formatear(alertas))
        if alertas.empty:
            return True
        destino = self.carpeta / f"alertas_{datetime.now():%Y%m%d_%H%M%S}.json"
        payload = alertas.assign(
            fecha_evento=alertas["fecha_evento"].dt.strftime("%Y-%m-%d")
        ).to_dict(orient="records")
        destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        return True


class Webhook(Notificador):
    """Publica en un webhook entrante de Slack o Teams."""

    def __init__(self, url: str):
        self.url = url

    def enviar(self, alertas: pd.DataFrame) -> bool:
        if alertas.empty:
            return True
        try:
            import requests
            r = requests.post(self.url, json={"text": formatear(alertas)}, timeout=15)
            return r.status_code < 300
        except Exception as exc:
            print(f"[webhook] fallo: {exc}")
            return False


class Email(Notificador):
    """Envia por SMTP. Las credenciales se leen del entorno, nunca del codigo."""

    def __init__(self, host: str, port: int, usuario: str, password: str,
                 destino: str):
        self.host, self.port = host, port
        self.usuario, self.password, self.destino = usuario, password, destino

    def enviar(self, alertas: pd.DataFrame) -> bool:
        if alertas.empty:
            return True
        try:
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            n_altas = int((alertas["severidad"] == "alta").sum())
            msg["Subject"] = f"Alertas del panel — {len(alertas)} nuevas ({n_altas} altas)"
            msg["From"], msg["To"] = self.usuario, self.destino
            msg.set_content(formatear(alertas))

            with smtplib.SMTP(self.host, self.port) as s:
                s.starttls()
                s.login(self.usuario, self.password)
                s.send_message(msg)
            return True
        except Exception as exc:
            print(f"[email] fallo: {exc}")
            return False
