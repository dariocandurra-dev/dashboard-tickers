/* ------------------------------------------------------------------
   Motor de indicadores del navegador.

   Replica exactamente src/indicators.py. Eso importa: las alertas se
   calculan en Python y el dashboard solo muestra, asi que si las dos
   implementaciones divergen el grafico contradice a la alerta.

   Dos detalles de pandas que hay que respetar para que los numeros den
   iguales y no "parecidos":

   1. ewm(adjust=False) es la recursion simple e[i] = a*x[i] + (1-a)*e[i-1]
      sembrada con el primer valor, NO el promedio ponderado acumulado.
   2. min_periods cuenta observaciones NO nulas. Como la linea MACD arranca
      en la rueda 25 (nula antes), su senal de 9 periodos recien queda
      definida en la rueda 33, no en la 8.
   ------------------------------------------------------------------ */

function sma(x, n) {
  const o = new Array(x.length).fill(null);
  let s = 0;
  for (let i = 0; i < x.length; i++) {
    s += x[i];
    if (i >= n) s -= x[i - n];
    if (i >= n - 1) o[i] = s / n;
  }
  return o;
}

/* ewm(alpha=..., adjust=False, min_periods=minp) tolerando nulos de entrada:
   un nulo no altera el estado y devuelve nulo, igual que pandas. */
function ewmAlpha(x, alpha, minp) {
  const o = new Array(x.length).fill(null);
  let e = null, vistos = 0;
  for (let i = 0; i < x.length; i++) {
    const v = x[i];
    if (v == null) continue;
    e = (e === null) ? v : alpha * v + (1 - alpha) * e;
    vistos++;
    if (vistos >= minp) o[i] = e;
  }
  return o;
}

const ema = (x, span) => ewmAlpha(x, 2 / (span + 1), span);

function macdCalc(x, fast = 12, slow = 26, signal = 9) {
  const ef = ema(x, fast), es = ema(x, slow);
  const linea = x.map((_, i) =>
    (ef[i] == null || es[i] == null) ? null : ef[i] - es[i]);
  const sig = ewmAlpha(linea, 2 / (signal + 1), signal);
  const hist = linea.map((v, i) => (v == null || sig[i] == null) ? null : v - sig[i]);
  return { macd: linea, sig, hist };
}

function rsiCalc(x, period = 14) {
  const gan = new Array(x.length).fill(null);
  const per = new Array(x.length).fill(null);
  for (let i = 1; i < x.length; i++) {
    const d = x[i] - x[i - 1];
    gan[i] = d > 0 ? d : 0;
    per[i] = d < 0 ? -d : 0;
  }
  const a = 1 / period;
  const ag = ewmAlpha(gan, a, period), ap = ewmAlpha(per, a, period);
  return x.map((_, i) => {
    if (ag[i] == null || ap[i] == null) return null;
    if (ap[i] === 0) return 100;
    const rs = ag[i] / ap[i];
    return 100 - 100 / (1 + rs);
  });
}

/* Volatilidad anualizada: desvio de retornos log por raiz de 252. */
function volCalc(x, n) {
  const r = new Array(x.length).fill(null);
  for (let i = 1; i < x.length; i++) r[i] = Math.log(x[i] / x[i - 1]);
  const o = new Array(x.length).fill(null);
  for (let i = n; i < x.length; i++) {
    let s = 0;
    for (let k = i - n + 1; k <= i; k++) s += r[k];
    const m = s / n;
    let v = 0;
    for (let k = i - n + 1; k <= i; k++) v += (r[k] - m) ** 2;
    o[i] = Math.sqrt(v / n) * Math.sqrt(252);   // ddof=0, como numpy
  }
  return o;
}

function drawdownCalc(x) {
  let pico = -Infinity;
  return x.map(v => { if (v > pico) pico = v; return v / pico - 1; });
}

/* ------------------------------------------------------------------
   Metricas de contexto de tendencia.
   ------------------------------------------------------------------ */

/* Pendiente de una media: variacion porcentual en `n` ruedas.
   Distingue el retroceso dentro de una tendencia alcista (media subiendo)
   del cambio de tendencia (media ya girada a la baja), que es la diferencia
   que el porcentaje de distancia por si solo no muestra. */
function pendiente(ma, n) {
  return ma.map((v, i) =>
    (v == null || i < n || ma[i - n] == null || ma[i - n] === 0)
      ? null : v / ma[i - n] - 1);
}

/* Caida desde el maximo de las ultimas `n` ruedas (252 = un anio bursatil).
   Distinto del drawdown historico: mide el castigo del ultimo anio, no el
   de toda la serie. Maximo movil con deque monotona decreciente: O(n). */
function drawdown52(x, n = 252) {
  const o = new Array(x.length).fill(null);
  const dq = [];                       // indices, valores decrecientes
  for (let i = 0; i < x.length; i++) {
    while (dq.length && x[dq[dq.length - 1]] <= x[i]) dq.pop();
    dq.push(i);
    if (dq[0] <= i - n) dq.shift();    // sale de la ventana
    o[i] = x[i] / x[dq[0]] - 1;
  }
  return o;
}

/* Distancia a la MA200 medida en jornadas de volatilidad.

   Es la correccion al problema central de comparar por porcentaje: en este
   panel la volatilidad anual va de 4% a 246%, asi que -18% en un papel
   tranquilo y -33% en uno volatil pueden ser el mismo grado de estiramiento.
   Dividir la distancia por la volatilidad DIARIA deja todo en una unidad
   comun y legible: cuantas jornadas promedio de movimiento falta recorrer
   para volver a la media.

   Se usa la volatilidad de 60 ruedas y no la de 20 a proposito: la ventana
   corta se infla por la misma caida que se esta midiendo y termina dividiendo
   por un numero mas grande justo cuando el papel se desploma, lo que disimula
   el derrumbe. En INTC la volatilidad de 20 ruedas pasó de 78% a 140% durante
   la caida; la de 60 quedo en 97%. */
function zDistancia(dist, vol) {
  return dist.map((d, i) => {
    const v = vol[i];
    if (d == null || v == null || v <= 0) return null;
    return d / (v / Math.sqrt(252));
  });
}

/* Calcula todo para una serie densa de cierres (sin nulos internos). */
function calcularTodo(c) {
  const { macd, sig, hist } = macdCalc(c);
  const s50 = sma(c, 50), s200 = sma(c, 200);
  const vol20 = volCalc(c, 20), vol60 = volCalc(c, 60);
  const dist200 = c.map((v, i) => s200[i] == null ? null : v / s200[i] - 1);
  return {
    c, s50, s200,
    macd, sig, hist,
    rsi: rsiCalc(c),
    vol20, vol60,
    dd: drawdownCalc(c),
    dd52: drawdown52(c, 252),
    dist200,
    pend200: pendiente(s200, 20),
    z200: zDistancia(dist200, vol60),
  };
}
