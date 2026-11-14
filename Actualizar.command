#!/bin/bash
# Actualizador para macOS y Linux. Doble clic para ejecutar.
# En macOS puede pedir permiso la primera vez: clic derecho -> Abrir.

cd "$(dirname "$0")" || exit 1

echo
echo "=========================================="
echo "  ACTUALIZAR PANEL DE 100 TICKERS"
echo "=========================================="
echo

fin() {
    echo
    read -n 1 -s -r -p "Presioná cualquier tecla para cerrar..."
    echo
    exit "$1"
}

# --- Buscar Python ---
PY=""
command -v python3 >/dev/null 2>&1 && PY=python3
[ -z "$PY" ] && command -v python >/dev/null 2>&1 && PY=python

if [ -z "$PY" ]; then
    echo "  NO SE ENCONTRÓ PYTHON EN ESTA COMPUTADORA"
    echo
    echo "  Descargalo de python.org/downloads e instalalo."
    echo "  Después volvé a abrir este archivo."
    fin 1
fi

# --- Preparar el entorno la primera vez ---
# Se verifica que las librerias IMPORTEN, no que la carpeta exista: si una
# instalacion anterior quedo por la mitad (red caida, ventana cerrada), la
# carpeta .venv existe pero esta incompleta, y hay que reinstalar igual.
necesita_instalar=1
if [ -x ".venv/bin/python" ]; then
    .venv/bin/python -c "import pandas, yfinance" >/dev/null 2>&1 && necesita_instalar=0
fi

if [ "$necesita_instalar" = "1" ]; then
    echo "Primera vez: preparando el entorno."
    echo "Esto tarda unos minutos y pasa una sola vez."
    echo
    [ -x ".venv/bin/python" ] || "$PY" -m venv .venv || { echo "No se pudo crear el entorno virtual."; fin 1; }
    .venv/bin/python -m pip install --upgrade pip --quiet
    if ! .venv/bin/python -m pip install -r requirements.txt; then
        echo
        echo "  FALLÓ LA INSTALACIÓN DE LAS LIBRERÍAS"
        echo "  Causa más común: la red bloquea la descarga."
        echo "  Probá desde tu red hogareña."
        fin 1
    fi
    echo
    echo "Entorno listo."
    echo
fi

# --- Actualizar ---
echo "Actualizando datos. Puede tardar varios minutos."
echo
if ! .venv/bin/python scripts/update_all.py; then
    echo
    echo "  LA ACTUALIZACIÓN NO TERMINÓ BIEN"
    echo "  Causa más común: no hay acceso a Yahoo Finance desde esta red."
    echo "  El dashboard anterior sigue funcionando."
    echo "  El detalle quedó en data/update.log"
    fin 1
fi

echo
echo "=========================================="
echo "  LISTO"
echo "=========================================="
echo
echo "Abriendo el dashboard actualizado..."
if command -v open >/dev/null 2>&1; then
    open Dashboard_Tickers.html
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open Dashboard_Tickers.html >/dev/null 2>&1
fi
fin 0
