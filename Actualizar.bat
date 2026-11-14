@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Actualizar panel de tickers

echo.
echo ==========================================
echo   ACTUALIZAR PANEL DE 100 TICKERS
echo ==========================================
echo.

rem --- Buscar Python en el sistema ---
set PY=
where python >nul 2>nul
if %errorlevel%==0 set PY=python
if defined PY goto tienepython
where py >nul 2>nul
if %errorlevel%==0 set PY=py
:tienepython
if not defined PY goto sinpython

rem --- Preparar el entorno la primera vez ---
rem Se verifica que las librerias IMPORTEN, no que la carpeta exista: si una
rem instalacion anterior quedo por la mitad, .venv existe pero esta incompleta.
if not exist ".venv\Scripts\python.exe" goto instalar
".venv\Scripts\python.exe" -c "import pandas, yfinance" >nul 2>nul
if %errorlevel%==0 goto yapreparado
echo La instalacion anterior quedo incompleta. Reintentando.
echo.

:instalar
echo Primera vez: preparando el entorno.
echo Esto tarda unos minutos y pasa una sola vez.
echo.
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto fallovenv
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %errorlevel% neq 0 goto falloinstalar
echo.
echo Entorno listo.
echo.

:yapreparado
echo Actualizando datos. Puede tardar varios minutos.
echo.
".venv\Scripts\python.exe" scripts\update_all.py
if %errorlevel% neq 0 goto falloactualizar

echo.
echo ==========================================
echo   LISTO
echo ==========================================
echo.
echo Abriendo el dashboard actualizado...
start "" "Dashboard_Tickers.html"
echo.
pause
exit /b 0

:sinpython
echo.
echo  NO SE ENCONTRO PYTHON EN ESTA COMPUTADORA
echo.
echo  Descargalo de python.org/downloads
echo  IMPORTANTE: en la primera pantalla del instalador,
echo  tilda la casilla "Add Python to PATH".
echo.
echo  Despues volve a hacer doble clic en este archivo.
echo.
pause
exit /b 1

:fallovenv
echo.
echo  No se pudo crear el entorno virtual.
echo  Probable causa: permisos de la carpeta.
echo  Proba mover la carpeta al Escritorio y repetir.
echo.
pause
exit /b 1

:falloinstalar
echo.
echo  FALLO LA INSTALACION DE LAS LIBRERIAS
echo.
echo  Causa mas comun: la red de la oficina bloquea la descarga.
echo  Proba desde tu red hogarena.
echo.
echo  Copia el texto de arriba si necesitas ayuda para resolverlo.
echo.
pause
exit /b 1

:falloactualizar
echo.
echo  LA ACTUALIZACION NO TERMINO BIEN
echo.
echo  Causa mas comun: no hay acceso a Yahoo Finance
echo  desde esta red. El dashboard anterior sigue funcionando.
echo.
echo  El detalle quedo guardado en data\update.log
echo.
pause
exit /b 1
