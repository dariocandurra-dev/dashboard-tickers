# Cómo usarlo

## Lo único que necesitás hacer ahora

Abrí **`Dashboard_Tickers.html`** con doble clic.

Se abre en el navegador y ya está: las 88 series con sus indicadores, señales y
alertas están adentro del archivo. No necesita Python, ni servidor, ni internet.
Lo podés mandar por mail, subirlo a una carpeta compartida o abrirlo desde un
pendrive, y funciona igual.

Qué vas a ver:

- **Cinta de amplitud** arriba: una barra por acción, ordenadas por distancia a su
  MA200. El estado del panel entero de un vistazo. Clic en cualquier barra abre esa acción.
- **Panel**: grilla filtrable por sector, país y posición respecto de la MA200,
  ordenable por cualquier columna, más la comparación en base 100.
- **Ficha por acción**: precio con MA50 y MA200, MACD con histograma, RSI, y los
  KPIs fundamentales cuando estén descargados.
- **Alertas**: agrupadas por severidad.
- **Calendario**: próximas presentaciones de balances.

---

## Cuando quieras actualizar los datos

Doble clic en **`Actualizar.bat`** (Windows) o **`Actualizar.command`** (Mac).

Eso es todo. La primera vez tarda unos minutos porque prepara el entorno solo;
después son segundos. Cuando termina abre el dashboard actualizado.

Si algo falla, la ventana te dice qué pasó en castellano y espera a que la leas
antes de cerrarse.

### Si preferís hacerlo a mano

### Preparar el entorno (una sola vez, 5 minutos)

Necesitás Python 3.10 o superior. Si no lo tenés, descargalo de python.org y
**en Windows tildá "Add Python to PATH"** en la primera pantalla del instalador.

Abrí una terminal dentro de la carpeta del proyecto:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Si PowerShell bloquea la activación, corré una vez:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Para verificar que quedó todo bien:
```bash
python scripts/verificar.py
```

### Actualizar

```bash
python scripts/update_all.py
```

Baja las cotizaciones nuevas, recalcula indicadores y señales, refresca los
fundamentales si vencieron, dispara las alertas y **regenera el HTML**. Cuando
termina, volvés a abrir `Dashboard_Tickers.html` y está al día.

### Completar lo que falta (una sola vez)

Doce series quedaron sin datos y SAP e INFY están pendientes de migrar al ADR.
Con acceso a internet:

```bash
python scripts/repair_missing.py
python scripts/stage2_indicators.py
python scripts/stage3_fundamentals.py --force
python scripts/build_html.py
```

El tercero tarda entre 5 y 15 minutos porque baja tres estados contables por
empresa con pausas para no chocar contra el límite de la API.

### Que se actualice solo

**Windows** — Programador de tareas → Crear tarea básica → diaria 19:30 →
"Iniciar un programa":
- Programa: `C:\ruta\al\proyecto\.venv\Scripts\python.exe`
- Argumentos: `scripts/update_all.py`
- Iniciar en: `C:\ruta\al\proyecto`

**macOS / Linux** — `crontab -e` y pegar la línea de `cron.example`.

**En la nube** — subí el repo a GitHub y el workflow de
`.github/workflows/actualizar.yml` corre solo, sin dejar la máquina prendida.

### Alertas por Slack o Teams

En el canal: Configuración → Aplicaciones → Incoming Webhooks → copiar la URL.

```bash
# Windows
$env:ALERT_WEBHOOK_URL="https://hooks.slack.com/services/..."
# macOS / Linux
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/..."

python scripts/update_all.py --canal webhook
```

Por mail: definí `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` y `ALERT_TO`,
y usá `--canal email`.

---

## Si algo falla

**`python no se reconoce como un comando`**
No quedó en el PATH. Reinstalá tildando la opción, o usá `py` en vez de `python`.

**`ModuleNotFoundError: No module named 'pandas'`**
El entorno virtual no está activo. Cuando lo está, ves `(.venv)` al principio de
la línea. Repetí el paso de activación.

**Yahoo Finance no responde desde la red de la oficina**
Es lo más probable: el proxy corporativo bloquea el dominio. Tres salidas, en
orden de practicidad: correr la actualización desde tu red hogareña, pedir a IT
que habiliten `query1.finance.yahoo.com` y `query2.finance.yahoo.com`, o mover la
automatización a GitHub Actions, que corre fuera de la red corporativa.

**`JSONDecodeError` al bajar fundamentales**
Límite de la API por exceso de pedidos. Esperá unos minutos y volvé a correr: el
caché no vuelve a pedir lo que ya bajó, así que retoma donde quedó.

**Un ticker aparece sin fundamentales**
Yahoo cubre bien Estados Unidos y flojo el resto. Mirá `data/fichas_incompletas.csv`
para ver cuáles y cuánto les falta.

---

## Nota sobre Streamlit

El proyecto también incluye `app.py`, una versión en Streamlit con los mismos
datos. Es útil si alguna vez querés una interfaz que consulte los datos en vivo,
pero requiere tener Python corriendo mientras la mirás. Para el uso diario, el
HTML es más práctico.
