"""
Diagnostico previo. Verifica que el entorno este en condiciones antes de la
primera corrida, y dice exactamente que falta cuando algo no esta.

Uso:  python scripts/verificar.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OK, FALLA, AVISO = "  [OK]   ", "  [FALLA]", "  [AVISO]"


def main() -> None:
    problemas = 0

    print("\nPython")
    v = sys.version_info
    if v >= (3, 10):
        print(f"{OK} version {v.major}.{v.minor}.{v.micro}")
    else:
        print(f"{FALLA} se requiere 3.10 o superior, hay {v.major}.{v.minor}")
        problemas += 1

    print("\nDependencias")
    for mod, paquete in [("pandas", "pandas"), ("numpy", "numpy"),
                         ("pyarrow", "pyarrow"), ("yfinance", "yfinance"),
                         ("streamlit", "streamlit"), ("plotly", "plotly")]:
        try:
            m = __import__(mod)
            print(f"{OK} {paquete} {getattr(m, '__version__', '')}")
        except ImportError:
            print(f"{FALLA} falta {paquete} -> pip install -r requirements.txt")
            problemas += 1

    print("\nArchivos del proyecto")
    from src import config as C
    for nombre, ruta, critico in [
        ("Excel histórico", C.RAW_XLSX, False),
        ("Maestro de tickers", C.MASTER_CSV, True),
        ("Precios", C.PRICES_LONG, True),
        ("Indicadores", C.DATA_DIR / "indicators.parquet", False),
        ("Señales", C.DATA_DIR / "signals.parquet", False),
    ]:
        if ruta.exists():
            print(f"{OK} {nombre}")
        elif critico:
            print(f"{FALLA} falta {nombre}: {ruta}")
            problemas += 1
        else:
            print(f"{AVISO} falta {nombre} (se genera al correr los scripts)")

    print("\nSalida a red (Yahoo Finance)")
    try:
        import yfinance as yf
        d = yf.Ticker("AAPL").history(period="5d")
        if d is not None and not d.empty:
            print(f"{OK} conectividad confirmada, último cierre AAPL "
                  f"{d['Close'].iloc[-1]:.2f}")
        else:
            print(f"{AVISO} respuesta vacía: posible bloqueo de red o límite de la API")
    except Exception as exc:
        print(f"{AVISO} sin acceso a Yahoo Finance ({type(exc).__name__})")
        print("         El panel funciona igual con los datos del Excel, pero no")
        print("         vas a poder reponer series ni bajar fundamentales.")

    print("\n" + ("Todo listo." if problemas == 0
                  else f"{problemas} problema(s) a resolver antes de seguir."))
    sys.exit(0 if problemas == 0 else 1)


if __name__ == "__main__":
    main()
