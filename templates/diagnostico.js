/* ------------------------------------------------------------------
   Motor de diagnostico tecnico.

   Responde la pregunta que el panel por si solo no contesta: de los papeles
   que estan debajo de su MA200, cuales son un retroceso dentro de una
   tendencia sana y cuales son una tendencia rota. Son situaciones opuestas
   que el porcentaje de distancia muestra igual.

   Reglas deterministas, sin aleatoriedad ni llamadas externas: con los
   mismos datos de entrada siempre sale el mismo resultado, y por eso se
   puede auditar y recalibrar.

   TRES DECISIONES QUE CONVIENE CONOCER ANTES DE TOCAR LOS UMBRALES:

   1. El "que tan lejos" se mide en z (jornadas de volatilidad), no en
      porcentaje. En este panel la volatilidad anual va de 4% a 246%: -18%
      en LOMA y -33% en GGAL son el mismo estiramiento. Un umbral en
      porcentaje marcaria extremo al volatil y normal al tranquilo, que es
      justo el error que se quiere evitar. El porcentaje queda como control
      secundario para que un activo muy quieto no figure como extremo por
      una caida trivial.

   2. El orden importa: gana la primera regla que da verdadero. Capitulacion
      se evalua ANTES que tendencia bajista porque casi todo lo muy sobrevendido
      esta ademas en tendencia bajista; lo que las separa es si el momento
      vendedor se esta agotando.

   3. "Vigilar rebote" NO es una compra: es contratendencia, el estado mas
      riesgoso del tablero. El texto lo dice explicitamente.
   ------------------------------------------------------------------ */

const DIAG_CFG = {
  // --- Sobreventa extrema (posible capitulacion) ---
  zExtremo:       -9,     // decil inferior del panel (p10 = -9,2)
  distExtremoMax: -0.06,  // ademas, al menos 6% debajo: evita falsos extremos
  rsiSobreventa:   35,

  // --- Retroceso en tendencia alcista ---
  // Sin piso en porcentaje a proposito: ponerlo contradice la normalizacion.
  // NVDA 20% debajo de su MA200 con volatilidad de 53% esta MENOS estirado
  // que LOMA 18% debajo con volatilidad de 29%. El z ya acota el rango.
  zPullbackMin:   -9,     // mas lejos que esto ya no es retroceso
  zPullbackMax:   -0.5,
  distPullbackMax: 0.01,  // tolera rozar la media por arriba
  rsiPullback:     48,
  pendMinima:      0.0,   // MA200 tiene que estar subiendo

  // --- Extension alcista ---
  zExtendido:      10,    // decil superior del panel (p90 = 10,4)
  rsiSobrecompra:  70,

  // --- Tendencia alcista sana ---
  rsiSanoMin: 45,
  rsiSanoMax: 68,
};

const DIAG_ESTADOS = {
  sin_datos:  { etiqueta: 'Sin MA200',            color: 'gris'  },
  rebote:     { etiqueta: 'Vigilar rebote',       color: 'ambar' },
  bajista:    { etiqueta: 'Tendencia bajista',    color: 'rojo'  },
  deterioro:  { etiqueta: 'Debilitándose',        color: 'naranja' },
  pullback:   { etiqueta: 'Retroceso en alza',    color: 'verde' },
  extendido:  { etiqueta: 'Extendido',            color: 'ambar' },
  alcista:    { etiqueta: 'Alcista sana',         color: 'verde' },
  neutral:    { etiqueta: 'Sin señal',            color: 'gris'  },
};

/* Estados que el filtro rapido "Oportunidades" deja a la vista. */
const DIAG_OPORTUNIDAD = ['pullback', 'rebote'];

/* Formato local: coma decimal, como el resto del panel. */
const _num = (v, d) => v.toFixed(d).replace('.', ',');
const _pc  = (v, d = 1) => v == null ? '—' :
  (v >= 0 ? '+' : '−') + _num(Math.abs(v) * 100, d) + '%';
const _pc0 = (v, d = 1) => v == null ? '—' : _num(Math.abs(v) * 100, d) + '%';

/* `d` es la foto de la ultima rueda de un papel:
   { dist, z, pend, rsi, hist, histPrev, ma50sobre200, dd52 } */
function generarDiagnosticoTecnico(d) {
  const K = DIAG_CFG;
  const faltan = d == null || d.dist == null || d.z == null;
  if (faltan) {
    return _salida('sin_datos',
      'Todavía no tiene 200 ruedas de historia, así que no hay MA200 para comparar.', d);
  }

  const macdMejora = d.hist != null && d.histPrev != null && d.hist > d.histPrev;
  const pendSube   = d.pend != null && d.pend > K.pendMinima;
  const pendBaja   = d.pend != null && d.pend < 0;
  const bajoMedia  = d.dist < 0;

  // 1. Sobreventa extrema con el momento vendedor aflojando
  if (bajoMedia && d.z <= K.zExtremo && d.dist <= K.distExtremoMax &&
      d.rsi != null && d.rsi <= K.rsiSobreventa && macdMejora) {
    return _salida('rebote',
      `Está ${_pc0(d.dist)} debajo de la MA200, un estiramiento de ${Math.abs(d.z).toFixed(0)} ` +
      `jornadas de volatilidad, con RSI en ${_num(d.rsi,0)} y el histograma del MACD ` +
      `achicándose: el momento vendedor afloja. Es un rebote contra la tendencia, ` +
      `el escenario más riesgoso del tablero.`, d);
  }

  // 2. Tendencia bajista confirmada: los dos soportes de tendencia rotos
  if (bajoMedia && pendBaja && d.ma50sobre200 === false) {
    return _salida('bajista',
      `Cotiza ${_pc0(d.dist)} debajo de una MA200 que además viene cayendo ` +
      `(${_pc(d.pend)} en 20 ruedas), con la MA50 por debajo de la MA200. ` +
      `No es un retroceso: es tendencia de fondo bajista.`, d);
  }

  // 3. Deterioro: uno solo de los dos soportes roto. Es el estado que separa
  //    el retroceso sano de la tendencia quebrada, y sin el casi todo cae en
  //    "sin señal" justo cuando la tendencia esta cambiando.
  if (bajoMedia && (pendBaja || d.ma50sobre200 === false)) {
    const cual = pendBaja
      ? `la MA200 ya giró a la baja (${_pc(d.pend)} en 20 ruedas) aunque la MA50 ` +
        `sigue por encima`
      : `la MA50 ya cruzó por debajo de la MA200, aunque la media larga todavía sube ` +
        `(${_pc(d.pend)} en 20 ruedas)`;
    return _salida('deterioro',
      `Cotiza ${_pc0(d.dist)} debajo de la MA200 y ${cual}. La tendencia se está ` +
      `dando vuelta pero el giro no está confirmado: conviene esperar.`, d);
  }

  // 4. Retroceso dentro de una tendencia alcista intacta
  if (d.dist <= K.distPullbackMax &&
      d.z >= K.zPullbackMin && d.z <= K.zPullbackMax &&
      pendSube && d.ma50sobre200 === true &&
      d.rsi != null && d.rsi < K.rsiPullback) {
    return _salida('pullback',
      `Cotiza ${_pc0(d.dist)} ${d.dist < 0 ? 'debajo de' : 'sobre'} su MA200, pero la media ` +
      `de largo plazo sigue subiendo (${_pc(d.pend)} en 20 ruedas), la MA50 no perdió a la ` +
      `MA200 y el RSI en ${_num(d.rsi,0)} sugiere agotamiento vendedor. Retroceso dentro ` +
      `de una tendencia que no se quebró.`, d);
  }

  // 5. Extension alcista
  if (!bajoMedia && (d.z >= K.zExtendido ||
      (d.rsi != null && d.rsi >= K.rsiSobrecompra))) {
    return _salida('extendido',
      `Está ${_pc0(d.dist)} por encima de la MA200` +
      (d.rsi != null ? ` con RSI en ${_num(d.rsi,0)}` : '') +
      `. La tendencia es alcista pero el precio viene estirado: entrar acá es ` +
      `comprar lejos del soporte.`, d);
  }

  // 6. Tendencia alcista sana
  if (!bajoMedia && d.ma50sobre200 === true && d.rsi != null &&
      d.rsi >= K.rsiSanoMin && d.rsi <= K.rsiSanoMax) {
    return _salida('alcista',
      `Cotiza ${_pc0(d.dist)} sobre la MA200, con MA50 por encima de MA200 y RSI en ` +
      `${_num(d.rsi,0)}. Tendencia alcista sin señales de agotamiento.`, d);
  }

  // 7. Resto
  return _salida('neutral',
    `Cotiza ${_pc0(d.dist)} ${bajoMedia ? 'debajo de' : 'sobre'} la MA200` +
    (d.pend != null ? `, con la media ${pendSube ? 'en alza' : pendBaja ? 'en baja' : 'plana'}` : '') +
    (d.rsi != null ? ` y RSI en ${_num(d.rsi,0)}` : '') +
    `. No cumple ninguna configuración definida.`, d);
}

function _salida(clave, resumen, d) {
  const e = DIAG_ESTADOS[clave];
  return {
    clave,
    estado: e.etiqueta,
    badgeColor: e.color,
    resumenTexto: resumen,
    esOportunidad: DIAG_OPORTUNIDAD.includes(clave),
    factores: d == null ? [] : [
      ['Distancia a MA200', d.dist == null ? '—' : _pc(d.dist)],
      ['Normalizada (z)', d.z == null ? '—'
        : (d.z >= 0 ? '+' : '−') + _num(Math.abs(d.z), 1) + ' jornadas'],
      ['Pendiente MA200 (20r)', d.pend == null ? '—' : _pc(d.pend, 2)],
      ['Cruce de medias', d.ma50sobre200 == null ? '—' :
        (d.ma50sobre200 ? 'Golden cross (MA50 > MA200)' : 'Death cross (MA50 < MA200)')],
      ['RSI 14', d.rsi == null ? '—' : _num(d.rsi, 0)],
      ['Caída desde máximo de 52 semanas', d.dd52 == null ? '—' : _pc(d.dd52)],
    ],
  };
}

/* Arma la foto de la ultima rueda a partir de las series calculadas. */
function fotoUltimaRueda(s) {
  if (!s || !s.c.length) return null;
  const n = s.c.length - 1;
  const ult = a => (a && a[n] != null) ? a[n] : null;
  const ma50 = ult(s.s50), ma200 = ult(s.s200);
  return {
    dist: ult(s.dist200),
    z: ult(s.z200),
    pend: ult(s.pend200),
    rsi: ult(s.rsi),
    hist: ult(s.hist),
    histPrev: (s.hist && n > 0 && s.hist[n - 1] != null) ? s.hist[n - 1] : null,
    ma50sobre200: (ma50 == null || ma200 == null) ? null : ma50 > ma200,
    dd52: ult(s.dd52),
  };
}
