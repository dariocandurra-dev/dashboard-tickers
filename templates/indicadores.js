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

/* Calcula todo para una serie densa de cierres (sin nulos internos). */
function calcularTodo(c) {
  const { macd, sig, hist } = macdCalc(c);
  return {
    c,
    s50: sma(c, 50), s200: sma(c, 200),
    macd, sig, hist,
    rsi: rsiCalc(c),
    vol20: volCalc(c, 20),
    dd: drawdownCalc(c),
  };
}
