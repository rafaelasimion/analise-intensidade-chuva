import { dataBR, dataHoraBR, escaparHtml, mesAno, num } from '../formato.js';

// Cores dos dados (paleta validada com o validador de daltonismo contra o papel #f3f6f4).
// Cada variável tem sempre a mesma cor em todos os gráficos.
export const COR = {
  chuva: '#2a78d6',
  temperatura: '#eb6834',
  umidade: '#1baf7a',
  vento: '#6250d6',
  etp: '#eb6834',
  etr: '#1baf7a',
  excedente: '#2a78d6',
  deficiencia: '#e34948',
};

// Cromo do gráfico
export const TINTA = {
  superficie: '#f3f6f4',
  texto: '#22303a',
  texto2: '#4f5d66',
  mudo: '#5e6b74',
  grade: '#dde5e1',
  gradeFina: '#e8eeeb',
  regua: '#b9c5bf',
};

export const FONTE = "'Archivo Variable', system-ui, -apple-system, 'Segoe UI', sans-serif";

export const reduzMovimento = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export const textoBase = { fontFamily: FONTE, color: TINTA.mudo, fontSize: 12 };

export function eixoValor(extra = {}) {
  return {
    type: 'value',
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { ...textoBase, formatter: (v) => num(v, Math.abs(v) < 10 && v % 1 !== 0 ? 1 : 0) },
    splitLine: { lineStyle: { color: TINTA.grade, width: 1 } },
    nameTextStyle: { ...textoBase, align: 'left' },
    ...extra,
  };
}

export function eixoTempo(extra = {}) {
  return {
    type: 'time',
    axisLine: { lineStyle: { color: TINTA.regua } },
    axisTick: { show: false },
    axisLabel: { ...textoBase, hideOverlap: true },
    splitLine: { show: false },
    ...extra,
  };
}

export function eixoCategoria(extra = {}) {
  return {
    type: 'category',
    axisLine: { lineStyle: { color: TINTA.regua } },
    axisTick: { show: false },
    axisLabel: { ...textoBase, hideOverlap: true },
    ...extra,
  };
}

export const legendaBase = {
  top: 0,
  left: 0,
  itemWidth: 14,
  itemHeight: 8,
  itemGap: 16,
  textStyle: { fontFamily: FONTE, color: TINTA.texto2, fontSize: 13 },
};

/** Formata o rótulo de tempo de acordo com o passo da série. */
export function rotuloTempo(valor, passo) {
  if (passo === '1M') return mesAno(valor);
  if (passo === '1D' || passo === '1W') return dataBR(valor);
  return dataHoraBR(valor);
}

/**
 * Dica (tooltip): valor em destaque, nome da série depois, chave em traço.
 * `linhas(params)` devolve [{cor, valor, unidade, nome}].
 */
export function dica(titulo, linhas) {
  const corpo = linhas
    .filter((l) => l.valor !== null && l.valor !== undefined)
    .map(
      (l) =>
        `<div class="dica__linha"><span class="dica__chave" style="background:${l.cor}"></span>` +
        `<strong>${escaparHtml(l.valor)}${l.unidade ? ` ${escaparHtml(l.unidade)}` : ''}</strong>` +
        `<span>${escaparHtml(l.nome)}</span></div>`,
    )
    .join('');
  return `<div class="dica__titulo">${escaparHtml(titulo)}</div>${corpo || '<div class="dica__linha">sem dado</div>'}`;
}

export const dicaBase = {
  confine: true,
  backgroundColor: '#fbfcfb',
  borderColor: TINTA.regua,
  borderWidth: 1,
  padding: [8, 10],
  textStyle: { fontFamily: FONTE, color: TINTA.texto, fontSize: 13 },
  extraCssText: 'box-shadow: 0 2px 8px rgba(34,48,58,.12); border-radius: 6px;',
};

export const ponteiroEixo = {
  type: 'line',
  lineStyle: { color: TINTA.texto2, width: 1 },
  label: { show: false },
};

/** Pares [tempo, valor] a partir da série colunar da API. */
export function pares(serie, campo) {
  if (!serie?.[campo]) return [];
  return serie.t.map((t, i) => [t, serie[campo][i]]);
}

export function temDados(serie, campo) {
  return Boolean(serie?.[campo]?.some((v) => v !== null && v !== undefined));
}
