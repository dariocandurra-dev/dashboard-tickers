# Panel de acciones y ETFs

**Ver el panel:** https://dariocandurra-dev.github.io/dashboard-tickers/

Se actualiza solo de lunes a viernes a las 19:30 de Buenos Aires, después del
cierre de Wall Street. Para forzar una actualización: pestaña **Actions** →
*Actualizar y publicar el panel* → **Run workflow**.

Para sumar o quitar papeles, editá `config/tickers_extra.csv` desde esta misma
página; al guardar, el panel se regenera con la lista nueva.

---

# Dashboard Financiero — Etapa 1: Capa de datos

Panel de 100 tickers, cierres diarios desde el 02-ene-2020 (el 01-ene fue feriado
en todas las plazas: la primera rueda efectiva es el 2).

## Estructura

```
config/tickers_master.csv   Maestro de 100 tickers con mapeo corregido a yfinance
src/config.py               Rutas, constantes y umbrales de QA
src/excel_loader.py         Parser del Excel historico (normaliza las 4 variantes de hoja)
src/api_loader.py           yfinance: reposicion full + refresh incremental
src/normalize.py            Calendario union, matriz ancha, base 100, QA
scripts/build_master.py     Regenera el maestro desde el Excel
scripts/stage1_build.py     Orquestador completo de la Etapa 1
scripts/repair_missing.py   Repone solo las series faltantes
data/                       Salidas en Parquet + reporte de calidad
```

## Uso

```bash
pip install -r requirements.txt
python scripts/stage1_build.py             # completo, con reposicion via API
python scripts/stage1_build.py --offline   # solo lo que hay en el Excel
python scripts/repair_missing.py           # solo las 12 series pendientes
```

## Salidas

| Archivo | Contenido |
|---|---|
| `prices_long.parquet` | Formato canonico: `ticker, date, close, source` |
| `prices_wide.parquet` | Matriz `fecha x ticker` sobre el calendario union |
| `base100.parquet` | Base 100 al 02-ene-2020 (comparacion de panel) |
| `base100_propio.parquet` | Base 100 al primer dato de cada serie (comparacion desde listado) |
| `qa_series.csv` | Cobertura, huecos y saltos por serie |
| `qa_report.md` | Reporte legible de calidad de datos |

## Decisiones de diseno

- **Formato largo como canonico.** La matriz ancha se deriva; asi conviven series
  con calendarios distintos sin inventar datos.
- **Calendario union, no dias habiles teoricos.** Conviven NYSE, Nasdaq, BYMA,
  XETR y NSE, con feriados distintos.
- **Forward-fill solo dentro de la vida de cada serie.** Antes del primer dato y
  despues del ultimo la serie queda en NaN: una accion que listo en 2021 no
  arrastra precios ficticios en 2020.
- **Cierre ajustado** (`auto_adjust=True`) en todo lo que baja de la API: es lo
  correcto para MACD, medias moviles y comparaciones en base 100.
- **Dos bases 100** porque responden preguntas distintas: performance relativa
  del panel vs. performance desde el debut de cada papel.

## Pendiente al cierre de la Etapa 1

12 series requieren reposicion via API (ver `data/qa_report.md`). El resto del
panel — 88 series, 145.803 observaciones, 1.732 ruedas — esta cargado y validado.

---

# Etapa 2 — Indicadores técnicos y señales

## Módulos

```
src/indicators.py             SMA/EMA, MACD, RSI, Bollinger, volatilidad, drawdown
src/signals.py                Estados, eventos de cruce e histéresis anti-whipsaw
scripts/stage2_indicators.py  Orquestador de la Etapa 2
```

## Indicadores calculados

| Grupo | Detalle |
|---|---|
| Medias simples | SMA 20 / 50 / 100 / 200 |
| Medias exponenciales | EMA 12 / 26 / 50 |
| MACD | Línea (12,26), señal (9), histograma |
| Momentum | RSI 14 con suavizado de Wilder |
| Volatilidad | Bandas de Bollinger (20, 2σ), ancho, %B; desvío anualizado 20d y 60d |
| Riesgo | Drawdown desde máximo acumulado |
| Derivados | Distancia % a MA200 y MA50, spread MA50/MA200 |

No hay ATR, OBV ni VWAP: el panel tiene solo cierres, sin OHLC ni volumen.

## Salidas

| Archivo | Contenido |
|---|---|
| `indicators.parquet` | Serie completa de indicadores por ticker y fecha |
| `signals.parquet` | Estados y eventos de cruce por ticker y fecha |
| `snapshot_tecnico.csv` | Foto del último día: la tabla que consume el dashboard |
| `eventos_recientes.csv` | Cruces de las últimas 10 ruedas |

## Decisiones de diseño

- **Cálculo sobre la serie observada, no sobre la matriz con forward-fill.** Un día
  rellenado repite el cierre anterior; sobre datos repetidos el MACD se aplana y
  los cruces de media móvil generan señales falsas.
- **Estado vs. evento.** El estado es la condición vigente (el precio está debajo
  de la MA200); el evento es el cruce puntual que la originó. La alerta se dispara
  con el evento, no con el estado: un papel que lleva ocho meses debajo de la MA200
  no debe notificar todos los días.
- **Histéresis en el cruce de MA200.** El estado confirmado solo pasa a "debajo"
  cuando el precio cierra bajo `MA200 × 0.99`, y vuelve a "arriba" al superar
  `MA200 × 1.01`. Reduce los cruces del panel de 4.330 a 2.455 (−43%) eliminando
  oscilaciones dentro de la banda. El cruce simple se conserva en paralelo.
- **`min_periods` completo en toda ventana.** Sin 200 ruedas no hay MA200: se
  prefiere el nulo al valor calculado sobre una ventana incompleta.
- Validación cruzada de MACD, señal y MA200 contra cálculo independiente:
  error máximo 0.0.

---

# Etapa 3 — Fundamentales, KPIs y calendario de balances

## Módulos

```
src/fundamentals.py              Extracción de perfil, KPIs y calendario vía yfinance
src/ficha.py                     Ensamblado de la ficha por acción
scripts/stage3_fundamentals.py   Orquestador con caché
tests/test_fundamentals.py       Validación sin red (28 checks)
```

## Qué extrae

| Bloque | Campos |
|---|---|
| Perfil | Nombre, sede (ciudad/estado/país), sector, industria, empleados, sitio, descripción |
| Resultados | Revenue y variación interanual, gross profit, operating income, net income, EBITDA |
| Márgenes | Bruto, operativo, neto, EBITDA — recalculados desde los estados contables |
| Retornos | ROE, ROA, deuda/patrimonio, FCF, conversión de FCF |
| Valuación | Market cap, P/E trailing y forward, price/book, EV/EBITDA, dividend yield, beta |
| Calendario | Próxima fecha de balance, si está confirmada, EPS estimado |

Los 12 ETFs se procesan aparte: AUM, expense ratio y yield en lugar de estados contables.

## Salidas

| Archivo | Contenido |
|---|---|
| `perfiles.parquet` | Identidad de cada emisor |
| `kpis.parquet` | Últimos resultados, márgenes y ratios |
| `earnings_calendar.parquet` | Próximas presentaciones |
| `fichas.parquet` / `.csv` | Una fila por ticker: fundamental + técnico consolidado |
| `cobertura_fundamental.csv` | Porcentaje de cada KPI efectivamente poblado |
| `fichas_incompletas.csv` | Tickers a complementar con otra fuente |

## Decisiones de diseño

- **Resolución de etiquetas por alias, no por índice fijo.** yfinance devuelve la
  línea de ingresos como `Total Revenue`, `TotalRevenue` u `Operating Revenue`
  según el emisor y la versión de la librería. `_pick` prueba una lista ordenada
  de alias y toma la primera que exista.
- **Márgenes recalculados, no tomados de `info`.** El campo `profitMargins` es TTM
  y no coincide con el último ejercicio cerrado: mostrarlo junto a los revenues
  anuales produce fichas que no cierran contra sí mismas.
- **Moneda de reporte separada de la de cotización.** Un ADR cotiza en USD pero
  reporta en su moneda local. Mezclar revenues de distinta moneda en un ranking
  es un error que no se ve hasta que alguien lo usa para decidir.
- **Caché con vencimiento.** Los fundamentales se refrescan cada 7 días y el
  calendario cada 1: los balances cambian por trimestre, no por rueda.
- **Fallos aislados por ticker.** Un emisor que no responde se registra en
  `fundamentales_errores.csv` y el lote sigue.
- **La ficha define qué es un dato faltante.** Esa convención vive en `ficha.py`
  y no en la UI, para que no convivan `-`, `N/D`, `nan` y `0` para el mismo caso.

## Estado

Lógica validada con fixtures que replican la estructura real de yfinance
(28 checks, todos pasando), incluyendo etiquetas alternativas, líneas ausentes,
patrimonio negativo, división por cero y caída de la API. Las fichas se arman
para los 100 tickers; los campos fundamentales quedan vacíos hasta ejecutar la
descarga con salida a red.

---

# Etapa 4 — Interfaz, alertas y automatización

## Módulos

```
app.py                        Dashboard Streamlit + Plotly
src/alerts.py                 Motor de alertas con deduplicación y notificadores
scripts/update_all.py         Orquestador de actualización diaria
.github/workflows/            Automatización por GitHub Actions
cron.example                  Alternativa por cron
```

## Ejecución

```bash
streamlit run app.py                                  # dashboard
python scripts/update_all.py                          # actualización + alertas
python scripts/update_all.py --canal webhook --webhook-url https://...
```

## Alertas

| Tipo | Severidad | Disparo |
|---|---|---|
| Perforación de MA200 | Alta | Cruce confirmado con histéresis |
| Death cross | Alta | MA50 cruza bajo MA200 |
| Recuperación de MA200 | Media | Cruce confirmado al alza |
| Golden cross | Media | MA50 cruza sobre MA200 |
| Balance próximo | Media | Presenta dentro de 7 días |
| RSI extremo | Baja | Sobrecompra ≥70 o sobreventa ≤30 |

**Deduplicación.** La clave incluye la fecha del *evento*, no la de la corrida: si
el cruce fue el 12-ago, la alerta es la misma el 13 y el 14. Solo un cruce nuevo
genera un disparo nuevo. Sin esto, el sistema reenvía todo todos los días y deja
de leerse en una semana.

**Canales.** Consola + JSON por default; webhook (Slack/Teams) y SMTP incluidos.
Las credenciales se leen de variables de entorno, nunca del código. Si el envío
falla, las alertas **no** se marcan como notificadas y se reintentan en la
corrida siguiente.

## Diseño de la interfaz

Instrumento de medición, no terminal de trading. Papel técnico claro, cifras en
IBM Plex Mono con numeración tabular —las columnas de números alinean por dígito
y se comparan de un vistazo— y color solo donde significa algo: verde pino sobre
la MA200, oxblood por debajo.

El elemento distintivo es la **cinta de amplitud** del encabezado: cien segmentos,
uno por ticker, ordenados por distancia a su MA200. El estado del panel entero en
un renglón, antes de abrir ninguna tabla.

Cuatro pestañas: Panel (grilla filtrable + comparación base 100), Ficha por acción
(precio con medias, MACD y RSI en subplots sincronizados, más los KPIs
fundamentales), Alertas agrupadas por severidad, y Calendario de balances.

## Automatización

`update_all.py` encadena precios → indicadores → fundamentales → alertas, con
**cada paso aislado**: si la descarga de fundamentales falla, los precios y las
alertas técnicas igual se procesan. Un dashboard con fundamentales de ayer sirve;
uno que no actualizó nada porque un endpoint devolvió 500, no.

El workflow corre 19:30 de Buenos Aires en días hábiles, después del cierre de
NYSE y Nasdaq.

---

# Optimización de peso del HTML

El archivo pasó de **5,82 MB a 1,04 MB (−82%)** sin perder ninguna funcionalidad.

## Qué pesaba

El bloque `series` era el 96% del archivo. Por cada acción viajaban seis arrays
—cierre, MA50, MA200, MACD, señal y RSI— de los cuales **cinco se derivan del
primero**. Eran 66 KB por ticker donde alcanzaban 12 KB.

## Qué se hizo

1. **Solo viajan los cierres.** `templates/indicadores.js` replica
   `src/indicators.py` y recalcula el resto en el navegador.
2. **Los huecos se guardan como excepción.** El calendario global es la unión de
   plazas con feriados distintos, así que una serie típica traía ~70 nulos sobre
   1.732 ruedas. Ahora va el cierre denso más la lista de ruedas no operadas.
3. **La base 100 se deriva.** Rebasear es dividir por el primer valor; mandar la
   serie ya rebaseada era guardar dos veces el mismo dato.

## Equivalencia con Python

El motor del navegador se validó contra `indicators.parquet`:
**error relativo máximo 4,9 × 10⁻¹⁴**. MACD, señal, histograma, RSI y drawdown
dan idénticos bit a bit. Esto importa porque las alertas se calculan en Python y
el dashboard solo muestra: si las dos implementaciones divergieran, el gráfico
contradiría a la alerta.

Dos detalles de pandas que hubo que replicar con exactitud:

- `ewm(adjust=False)` es la recursión simple sembrada con el primer valor, no el
  promedio ponderado acumulado.
- `min_periods` cuenta observaciones no nulas. Como la línea MACD arranca en la
  rueda 25, su señal de 9 períodos queda definida en la rueda 33, no en la 8.

## Rendimiento

Los indicadores se calculan por demanda, una sola vez por ticker y con caché:
abrir el archivo no dispara ningún cálculo, porque el panel y el mapa leen la
foto ya calculada en Python. Forzar el cálculo de las 88 series completas tarda
125 ms.

Con el panel completo de 127 series el archivo queda en torno a **1,5 MB**.
