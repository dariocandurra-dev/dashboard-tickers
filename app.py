"""
ETAPA 4 - Interfaz del panel.

    streamlit run app.py

Lenguaje visual: instrumento de medicion, no terminal de trading. Fondo claro de
papel tecnico, cifras en monoespaciada tabular (las columnas de numeros alinean
por digito y se comparan de un vistazo), y color usado solo donde significa algo
—verde pino y oxblood para estado de tendencia—, nunca como decoracion.

El elemento distintivo es la cinta de amplitud del encabezado: cien segmentos,
uno por ticker, ordenados por distancia a su MA200. Es el estado del panel
completo en un renglon, antes de abrir ninguna tabla.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import config as C

# --- Sistema de diseno ----------------------------------------------------
PAPEL = "#F7F6F3"
TINTA = "#15181C"
TENUE = "#6B6F76"
GRILLA = "#E3E1DB"
ALZA = "#157A5B"
BAJA = "#9E2B25"
ACENTO = "#2E3A8C"

st.set_page_config(page_title="Panel de 100 tickers", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
.stApp {{ background:{PAPEL}; color:{TINTA};
          font-family:'IBM Plex Sans',system-ui,sans-serif; }}
h1,h2,h3,h4 {{ font-family:'IBM Plex Sans',sans-serif; font-weight:600;
               letter-spacing:-.015em; color:{TINTA}; }}
h1 {{ font-size:1.55rem; margin-bottom:.1rem; }}
.eyebrow {{ font-family:'IBM Plex Mono',monospace; font-size:.7rem;
            letter-spacing:.14em; text-transform:uppercase; color:{TENUE}; }}
.cifra {{ font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums;
          font-size:1.5rem; font-weight:600; line-height:1.1; }}
.dato {{ font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums; }}
.alza {{ color:{ALZA}; }} .baja {{ color:{BAJA}; }}
.tarjeta {{ background:#FFF; border:1px solid {GRILLA}; border-radius:3px;
            padding:.85rem 1rem; }}
.regla {{ border-top:1px solid {GRILLA}; margin:1.1rem 0 .9rem; }}
[data-testid="stSidebar"] {{ background:#FFF; border-right:1px solid {GRILLA}; }}
.stDataFrame {{ font-family:'IBM Plex Mono',monospace; }}
</style>""", unsafe_allow_html=True)

PLOT = dict(paper_bgcolor=PAPEL, plot_bgcolor="#FFFFFF",
            font=dict(family="IBM Plex Mono, monospace", size=11, color=TINTA),
            margin=dict(l=8, r=8, t=28, b=8),
            xaxis=dict(gridcolor=GRILLA, zeroline=False),
            yaxis=dict(gridcolor=GRILLA, zeroline=False))


# --- Carga ----------------------------------------------------------------
@st.cache_data(ttl=900)
def cargar():
    d = {}
    def leer(nombre, parquet=True):
        p = C.DATA_DIR / nombre
        if not p.exists():
            return None
        return pd.read_parquet(p) if parquet else pd.read_csv(p)

    d["master"] = C.load_master()
    d["ind"] = leer("indicators.parquet")
    d["sig"] = leer("signals.parquet")
    d["b100"] = leer("base100.parquet")
    d["snap"] = leer("snapshot_tecnico.csv", parquet=False)
    d["fichas"] = leer("fichas.parquet")
    d["cal"] = leer("earnings_calendar.parquet")
    return d


D = cargar()
if D["ind"] is None:
    st.error("No hay indicadores calculados. Corré `python scripts/stage2_indicators.py` "
             "y volvé a cargar la página.")
    st.stop()

snap = D["snap"].copy()
snap["date"] = pd.to_datetime(snap["date"])
CORTE = snap["date"].max()


# --- Cinta de amplitud (elemento distintivo) ------------------------------
def cinta_amplitud(s: pd.DataFrame) -> go.Figure:
    """Un segmento por ticker, ordenado por distancia a su MA200."""
    d = s.dropna(subset=["dist_ma200"]).sort_values("dist_ma200")
    fig = go.Figure(go.Bar(
        x=d["dist_ma200"], y=[1] * len(d), orientation="h",
        base=0, width=1,
        marker=dict(color=[ALZA if v >= 0 else BAJA for v in d["dist_ma200"]],
                    line=dict(width=0)),
        customdata=d[["ticker", "empresa"]],
        hovertemplate="<b>%{customdata[0]}</b> %{customdata[1]}<br>"
                      "%{x:+.1%} vs MA200<extra></extra>"))
    fig.update_layout(**{**PLOT, "margin": dict(l=0, r=0, t=4, b=18)},
                      height=74, showlegend=False, barmode="overlay", bargap=0.15)
    fig.update_yaxes(visible=False)
    fig.update_xaxes(tickformat="+.0%", gridcolor=GRILLA, zeroline=True,
                     zerolinecolor=TINTA, zerolinewidth=1)
    return fig


# --- Encabezado -----------------------------------------------------------
izq, der = st.columns([3, 2])
with izq:
    st.markdown('<div class="eyebrow">Panel multimercado</div>', unsafe_allow_html=True)
    st.markdown("# 100 tickers")
    st.markdown(f'<span class="dato" style="color:{TENUE}">Cierres al '
                f'{CORTE:%d-%m-%Y} · {len(snap)} series activas</span>',
                unsafe_allow_html=True)
with der:
    arriba = int(snap["above_ma200_conf"].fillna(False).sum())
    abajo = len(snap) - arriba
    alcistas = int((snap["tendencia_larga"] == "alcista").sum())
    a, b, c = st.columns(3)
    for col, val, lab, cls in (
        (a, arriba, "sobre MA200", "alza"), (b, abajo, "bajo MA200", "baja"),
        (c, alcistas, "tendencia alcista", "")):
        col.markdown(f'<div class="cifra {cls}">{val}</div>'
                     f'<div class="eyebrow">{lab}</div>', unsafe_allow_html=True)

st.plotly_chart(cinta_amplitud(snap), width="stretch",
                config={"displayModeBar": False})
st.markdown('<div class="regla"></div>', unsafe_allow_html=True)


# --- Filtros --------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="eyebrow">Filtros</div>', unsafe_allow_html=True)
    sectores = st.multiselect("Sector", sorted(snap["sector"].dropna().unique()))
    paises = st.multiselect("País", sorted(snap["pais"].dropna().unique()))
    estado = st.radio("Respecto de la MA200", ["Todos", "Por encima", "Por debajo"])
    st.markdown('<div class="regla"></div>', unsafe_allow_html=True)
    st.markdown('<div class="eyebrow">Cobertura</div>', unsafe_allow_html=True)
    st.markdown(f'<span class="dato">{len(snap)} de {len(D["master"])} '
                f'con serie de precios</span>', unsafe_allow_html=True)

f = snap.copy()
if sectores:
    f = f[f["sector"].isin(sectores)]
if paises:
    f = f[f["pais"].isin(paises)]
if estado == "Por encima":
    f = f[f["above_ma200_conf"].fillna(False)]
elif estado == "Por debajo":
    f = f[~f["above_ma200_conf"].fillna(True)]


# --- Pestañas -------------------------------------------------------------
t_panel, t_ficha, t_alertas, t_cal = st.tabs(
    ["Panel", "Ficha por acción", "Alertas", "Calendario de balances"])

with t_panel:
    cols = ["ticker", "empresa", "sector", "close", "dist_ma200", "rsi14",
            "macd_hist", "vol20", "drawdown", "tendencia_larga"]
    tabla = f[[c for c in cols if c in f.columns]].copy()
    st.dataframe(
        tabla.style.format({
            "close": "{:,.2f}", "dist_ma200": "{:+.1%}", "rsi14": "{:.0f}",
            "macd_hist": "{:+.2f}", "vol20": "{:.1%}", "drawdown": "{:.1%}"})
        .map(lambda v: f"color:{ALZA}" if isinstance(v, (int, float)) and v > 0
             else (f"color:{BAJA}" if isinstance(v, (int, float)) and v < 0 else ""),
             subset=["dist_ma200", "macd_hist"]),
        width="stretch", height=430, hide_index=True)

    st.markdown('<div class="eyebrow">Evolución comparada · base 100</div>',
                unsafe_allow_html=True)
    if D["b100"] is not None:
        disp = [t for t in f["ticker"] if t in D["b100"].columns]
        sel = st.multiselect("Series", disp, default=disp[:5], key="b100sel")
        if sel:
            fig = go.Figure()
            for t in sel:
                s = D["b100"][t].dropna()
                fig.add_trace(go.Scatter(x=s.index, y=s, name=t, mode="lines",
                                         line=dict(width=1.4)))
            fig.add_hline(y=100, line=dict(color=TENUE, width=1, dash="dot"))
            fig.update_layout(**PLOT, height=380, hovermode="x unified",
                              legend=dict(orientation="h", y=1.09))
            st.plotly_chart(fig, width="stretch")

with t_ficha:
    tk = st.selectbox("Acción", sorted(f["ticker"]), key="ficha_tk")
    g = D["ind"][D["ind"]["ticker"] == tk].set_index("date").sort_index()
    fila = snap[snap["ticker"] == tk].iloc[0]

    st.markdown(f"### {fila['empresa']}")
    m = st.columns(5)
    for col, lab, val in (
        (m[0], "Cierre", f"{fila['close']:,.2f}"),
        (m[1], "vs MA200", f"{fila['dist_ma200']:+.1%}"),
        (m[2], "RSI 14", f"{fila['rsi14']:.0f}"),
        (m[3], "Vol. 20d", f"{fila['vol20']:.1%}"),
        (m[4], "Drawdown", f"{fila['drawdown']:.1%}")):
        col.markdown(f'<div class="tarjeta"><div class="eyebrow">{lab}</div>'
                     f'<div class="dato" style="font-size:1.15rem">{val}</div></div>',
                     unsafe_allow_html=True)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[.56, .24, .20], vertical_spacing=.035,
                        subplot_titles=("Precio y medias móviles", "MACD", "RSI 14"))
    fig.add_trace(go.Scatter(x=g.index, y=g["close"], name="Cierre",
                             line=dict(color=TINTA, width=1.5)), 1, 1)
    for c, col, dash in (("sma50", ACENTO, "solid"), ("sma200", BAJA, "dash")):
        if c in g:
            fig.add_trace(go.Scatter(x=g.index, y=g[c], name=c.upper(),
                                     line=dict(color=col, width=1, dash=dash)), 1, 1)
    fig.add_trace(go.Bar(x=g.index, y=g["macd_hist"], name="Histograma",
                         marker=dict(color=[ALZA if v >= 0 else BAJA
                                            for v in g["macd_hist"].fillna(0)],
                                     line=dict(width=0))), 2, 1)
    fig.add_trace(go.Scatter(x=g.index, y=g["macd"], name="MACD",
                             line=dict(color=TINTA, width=1)), 2, 1)
    fig.add_trace(go.Scatter(x=g.index, y=g["macd_signal"], name="Señal",
                             line=dict(color=ACENTO, width=1)), 2, 1)
    fig.add_trace(go.Scatter(x=g.index, y=g["rsi14"], name="RSI",
                             line=dict(color=ACENTO, width=1)), 3, 1)
    for y in (70, 30):
        fig.add_hline(y=y, row=3, col=1,
                      line=dict(color=TENUE, width=.8, dash="dot"))
    fig.update_layout(**PLOT, height=680, showlegend=False, hovermode="x unified")
    fig.update_xaxes(gridcolor=GRILLA)
    fig.update_yaxes(gridcolor=GRILLA)
    st.plotly_chart(fig, width="stretch")

    st.markdown('<div class="eyebrow">Ficha fundamental</div>', unsafe_allow_html=True)
    fi = D["fichas"]
    row = fi[fi["ticker"] == tk] if fi is not None else None
    if row is None or row.empty or pd.isna(row.iloc[0].get("revenue")):
        st.info("Sin datos fundamentales todavía. Ejecutá "
                "`python scripts/stage3_fundamentals.py --force` con salida a red.")
    else:
        r = row.iloc[0]
        st.markdown(f"**{r.get('nombre','')}** · {r.get('industria','')} · "
                    f"{r.get('hq','')} · {int(r['empleados']):,} empleados"
                    if pd.notna(r.get("empleados")) else f"**{r.get('nombre','')}**")
        k = st.columns(4)
        items = [("Revenue", r.get("revenue"), "{:,.0f}"),
                 ("Var. i/a", r.get("revenue_yoy"), "{:+.1%}"),
                 ("Margen neto", r.get("margen_neto"), "{:.1%}"),
                 ("ROE", r.get("roe"), "{:.1%}"),
                 ("P/E", r.get("pe_trailing"), "{:.1f}"),
                 ("EV/EBITDA", r.get("ev_ebitda"), "{:.1f}"),
                 ("Deuda/Patrim.", r.get("deuda_patrimonio"), "{:.2f}"),
                 ("Market cap", r.get("market_cap"), "{:,.0f}")]
        for i, (lab, val, fmt) in enumerate(items):
            txt = fmt.format(val) if pd.notna(val) else "—"
            k[i % 4].markdown(f'<div class="tarjeta" style="margin-bottom:.5rem">'
                              f'<div class="eyebrow">{lab}</div>'
                              f'<div class="dato">{txt}</div></div>',
                              unsafe_allow_html=True)
        if pd.notna(r.get("moneda_reporte")) and r.get("moneda_reporte") not in ("", "USD"):
            st.caption(f"Cifras contables en {r['moneda_reporte']}; "
                       f"la cotización es en {r.get('currency','USD')}.")

with t_alertas:
    from src import alerts as A
    tec = A.alertas_tecnicas(D["sig"], D["master"])
    bal = A.alertas_balance(D["cal"], D["master"], dias=A.DIAS_AVISO_BALANCE)
    rsi = A.alertas_rsi(snap, D["master"])
    todas = [x for x in (tec, bal, rsi) if not x.empty]

    if not todas:
        st.markdown("Ninguna condición de alerta activa en el panel.")
    else:
        t = pd.concat(todas, ignore_index=True)
        for sev, etiqueta in (("alta", "Requieren atención"),
                              ("media", "Cambios de tendencia"),
                              ("baja", "Informativas")):
            sub = t[t["severidad"] == sev]
            if sub.empty:
                continue
            st.markdown(f'<div class="eyebrow">{etiqueta} · {len(sub)}</div>',
                        unsafe_allow_html=True)
            st.dataframe(sub[["ticker", "empresa", "fecha_evento", "detalle"]],
                         width="stretch", hide_index=True)

with t_cal:
    from src import alerts as A
    if D["cal"] is None or D["cal"].empty:
        st.info("Sin calendario de balances. Ejecutá "
                "`python scripts/stage3_fundamentals.py` con salida a red.")
    else:
        c = D["cal"].copy()
        c["proximo_balance"] = pd.to_datetime(c["proximo_balance"], errors="coerce")
        c = c.dropna(subset=["proximo_balance"]).sort_values("proximo_balance")
        c["dias"] = (c["proximo_balance"] - pd.Timestamp.now().normalize()).dt.days
        c = c[c["dias"] >= 0].merge(D["master"][["ticker", "empresa"]],
                                    on="ticker", how="left")
        prox = c[c["dias"] <= A.DIAS_AVISO_BALANCE]
        if not prox.empty:
            st.markdown(f'<div class="eyebrow">Próximos 7 días · {len(prox)}</div>',
                        unsafe_allow_html=True)
            st.dataframe(prox[["ticker", "empresa", "proximo_balance", "dias",
                               "balance_confirmado"]],
                         width="stretch", hide_index=True)
        st.markdown('<div class="eyebrow">Calendario completo</div>',
                    unsafe_allow_html=True)
        st.dataframe(c[["ticker", "empresa", "proximo_balance", "dias",
                        "balance_confirmado"]],
                     width="stretch", hide_index=True)
