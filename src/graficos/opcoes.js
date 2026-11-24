import { dataBR, mesAno, num } from '../formato.js';
import {
  COR, FONTE, TINTA, dica, dicaBase, eixoCategoria, eixoTempo, eixoValor, legendaBase, pares, ponteiroEixo,
  rotuloTempo,
} from './tema.js';

export const NOME_PASSO = { '15min': 'intervalo de 15 min', '1h': 'hora', '1D': 'dia', '1W': 'semana', '1M': 'mês' };
export const POR_PASSO = { '15min': 'a cada 15 min', '1h': 'por hora', '1D': 'por dia', '1W': 'por semana', '1M': 'por mês' };
const NO_PASSO = { '15min': 'em 15 min', '1h': 'na hora', '1D': 'no dia', '1W': 'na semana', '1M': 'no mês' };

const tituloPainel = (texto, top) => ({
  type: 'text',
  left: 0,
  top,
  style: { text: texto, fill: TINTA.texto2, font: `500 13px ${FONTE}` },
});

/* ------------------------------------------------------------------ */
/* Pluviograma: chuva por intervalo (barras caindo do topo) + acumulada */
/* ------------------------------------------------------------------ */

export function opcaoPluviograma(serie, passo) {
  const chuva = pares(serie, 'chuva_mm');
  const acum = pares(serie, 'chuva_acum_mm');
  const ultimo = [...acum].reverse().find((p) => p[1] !== null);
  const total = ultimo ? ultimo[1] : null;
  return {
    graphic: [
      tituloPainel(`Chuva ${POR_PASSO[passo]} (mm)`, 0),
      tituloPainel('Chuva acumulada no período (mm)', '61%'),
    ],
    grid: [
      { left: 44, right: 96, top: 28, height: '48%' },
      { left: 44, right: 96, top: '68%', bottom: 28 },
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: ponteiroEixo,
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        if (i === undefined) return '';
        return dica(rotuloTempo(serie.t[i], passo), [
          { cor: COR.chuva, valor: num(serie.chuva_mm?.[i], 1), unidade: 'mm', nome: NO_PASSO[passo] },
          { cor: COR.chuva, valor: num(serie.chuva_acum_mm?.[i], 1), unidade: 'mm', nome: 'acumulada' },
        ]);
      },
    },
    xAxis: [
      eixoTempo({ gridIndex: 0, position: 'top', axisLabel: { show: false }, axisLine: { lineStyle: { color: TINTA.texto2 } } }),
      eixoTempo({ gridIndex: 1 }),
    ],
    yAxis: [
      eixoValor({ gridIndex: 0, inverse: true, splitNumber: 3, minorTick: { show: false } }),
      eixoValor({ gridIndex: 1, splitNumber: 2, min: 0 }),
    ],
    series: [
      {
        name: 'Chuva no intervalo',
        type: 'bar',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: chuva,
        barMaxWidth: 24,
        barMinWidth: 1,
        itemStyle: { color: COR.chuva, borderRadius: [0, 0, 4, 4] },
        emphasis: { itemStyle: { color: '#1c5cab' } },
        animationDuration: 900,
        animationEasing: 'cubicOut',
      },
      {
        name: 'Chuva acumulada',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: acum,
        showSymbol: false,
        lineStyle: { width: 2, color: COR.chuva, cap: 'round', join: 'round' },
        itemStyle: { color: COR.chuva },
        areaStyle: { color: COR.chuva, opacity: 0.1 },
        endLabel: {
          show: total !== null,
          formatter: () => `${num(total, 1)} mm`,
          color: TINTA.texto,
          fontFamily: FONTE,
          fontSize: 15,
          fontWeight: 600,
          distance: 8,
        },
        animation: false,
      },
    ],
  };
}

/* ------------------------------------------------------------------ */
/* Gráficos pequenos do painel                                        */
/* ------------------------------------------------------------------ */

function baseTempo(passo, extra = {}) {
  return {
    grid: { left: 40, right: 16, top: 12, bottom: 28, ...extra.grid },
    xAxis: eixoTempo(),
    yAxis: eixoValor(extra.yAxis),
    tooltip: { ...dicaBase, trigger: 'axis', axisPointer: ponteiroEixo },
    animation: false,
  };
}

export function opcaoIntensidade(serie, passo, noIntervalo = 'em 15 min') {
  return {
    ...baseTempo(passo),
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: ponteiroEixo,
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        return dica(rotuloTempo(serie.t[i], passo), [
          { cor: COR.chuva, valor: num(serie.intensidade_max_mm_h?.[i], 1), unidade: 'mm/h', nome: `maior intensidade ${noIntervalo}` },
        ]);
      },
    },
    series: [
      {
        name: 'Intensidade máxima',
        type: 'bar',
        data: pares(serie, 'intensidade_max_mm_h'),
        barMaxWidth: 24,
        barMinWidth: 1,
        itemStyle: { color: COR.chuva, borderRadius: [4, 4, 0, 0] },
      },
    ],
  };
}

export function opcaoTemperatura(serie, passo) {
  const temMax = serie.temp_max_c?.some((v) => v !== null);
  const faixa = serie.t.map((t, i) => {
    const a = serie.temp_min_c?.[i];
    const b = serie.temp_max_c?.[i];
    return [t, a !== null && b !== null && a !== undefined && b !== undefined ? b - a : null];
  });
  const series = [];
  if (temMax && passo !== '15min') {
    series.push(
      {
        name: 'mín',
        type: 'line',
        data: pares(serie, 'temp_min_c'),
        stack: 'faixa',
        symbol: 'none',
        lineStyle: { opacity: 0 },
        silent: true,
      },
      {
        name: 'Faixa mín–máx',
        type: 'line',
        data: faixa,
        stack: 'faixa',
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { color: COR.temperatura, opacity: 0.14 },
        silent: true,
      },
    );
  }
  series.push({
    name: 'Média',
    type: 'line',
    data: pares(serie, 'temp_c'),
    showSymbol: false,
    lineStyle: { width: 2, color: COR.temperatura },
    itemStyle: { color: COR.temperatura },
  });
  return {
    ...baseTempo(passo, { yAxis: { scale: true } }),
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: ponteiroEixo,
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        return dica(rotuloTempo(serie.t[i], passo), [
          { cor: COR.temperatura, valor: num(serie.temp_c?.[i], 1), unidade: '°C', nome: 'média' },
          { cor: COR.temperatura, valor: serie.temp_max_c ? num(serie.temp_max_c[i], 1) : null, unidade: '°C', nome: 'máxima' },
          { cor: COR.temperatura, valor: serie.temp_min_c ? num(serie.temp_min_c[i], 1) : null, unidade: '°C', nome: 'mínima' },
        ]);
      },
    },
    series,
  };
}

export function opcaoUmidade(serie, passo) {
  return {
    ...baseTempo(passo, { yAxis: { min: 0, max: 100 } }),
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: ponteiroEixo,
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        return dica(rotuloTempo(serie.t[i], passo), [
          { cor: COR.umidade, valor: num(serie.ur_pct?.[i], 0), unidade: '%', nome: 'umidade relativa' },
        ]);
      },
    },
    series: [
      {
        name: 'Umidade relativa',
        type: 'line',
        data: pares(serie, 'ur_pct'),
        showSymbol: false,
        lineStyle: { width: 2, color: COR.umidade },
        itemStyle: { color: COR.umidade },
      },
    ],
  };
}

export function opcaoVento(serie, passo) {
  const temRajada = serie.vento_max_ms?.some((v) => v !== null);
  const series = [
    {
      name: 'Velocidade média',
      type: 'line',
      data: pares(serie, 'vento_ms'),
      showSymbol: false,
      lineStyle: { width: 2, color: COR.vento },
      itemStyle: { color: COR.vento },
    },
  ];
  if (temRajada) {
    series.push({
      name: 'Rajada máxima',
      type: 'line',
      data: pares(serie, 'vento_max_ms'),
      showSymbol: false,
      lineStyle: { width: 1, color: COR.vento, opacity: 0.55 },
      itemStyle: { color: COR.vento, opacity: 0.55 },
    });
  }
  return {
    ...baseTempo(passo, { grid: { top: 36 }, yAxis: { min: 0 } }),
    legend: temRajada ? { ...legendaBase } : undefined,
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: ponteiroEixo,
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        return dica(rotuloTempo(serie.t[i], passo), [
          { cor: COR.vento, valor: num(serie.vento_ms?.[i], 1), unidade: 'm/s', nome: 'média' },
          { cor: COR.vento, valor: temRajada ? num(serie.vento_max_ms?.[i], 1) : null, unidade: 'm/s', nome: 'rajada' },
        ]);
      },
    },
    series,
  };
}

/* ------------------------------------------------------------------ */
/* Barras por período (anos, meses…)                                  */
/* ------------------------------------------------------------------ */

export function opcaoBarrasChuva(
  linhas, rotulo = (l) => l.periodo, campo = 'chuva_mm', unidade = 'mm', incompleto = () => false, yMax = undefined,
) {
  const categorias = linhas.map(rotulo);
  return {
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    xAxis: eixoCategoria({ data: categorias }),
    yAxis: eixoValor({ min: 0, max: yMax }),
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(34,48,58,0.06)' } },
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        const l = linhas[i];
        return dica(categorias[i], [
          { cor: COR.chuva, valor: num(l?.[campo], 1), unidade, nome: 'chuva' },
          l?.dias_chuva !== undefined ? { cor: COR.chuva, valor: String(l.dias_chuva), unidade: '', nome: 'dias com chuva ≥ 1 mm' } : null,
          l && incompleto(l) ? { cor: TINTA.regua, valor: String(l.dias_com_dados), unidade: '', nome: 'dias com dados (período incompleto)' } : null,
        ].filter(Boolean));
      },
    },
    animation: false,
    series: [
      {
        name: 'Chuva',
        type: 'bar',
        data: linhas.map((l) => ({
          value: l[campo],
          itemStyle: incompleto(l) ? { color: COR.chuva, opacity: 0.4 } : undefined,
        })),
        barMaxWidth: 24,
        barMinWidth: 2,
        itemStyle: { color: COR.chuva, borderRadius: [4, 4, 0, 0] },
      },
    ],
  };
}

/* ------------------------------------------------------------------ */
/* Eventos: duração × intensidade média                               */
/* ------------------------------------------------------------------ */

export function opcaoEventos(eventos, colunaPico = 'i15_mm_h', nomePico = 'pico em 15 min') {
  const minimoH = colunaPico === 'i60_mm_h' ? 1 : 0.25;
  const pontos = eventos.map((e) => [Math.max(e.duracao_min / 60, minimoH), e.intensidade_media_mm_h, e.evento]);
  const dicaEvento = (p) => {
    const e = eventos[p.dataIndex];
    return dica(`Evento ${e.evento} – ${dataBR(e.inicio)}`, [
      { cor: COR.chuva, valor: num(e.intensidade_media_mm_h, 1), unidade: 'mm/h', nome: 'intensidade média' },
      { cor: COR.chuva, valor: num(e.chuva_mm, 1), unidade: 'mm', nome: 'chuva' },
      { cor: COR.chuva, valor: num(e.duracao_min / 60, 2), unidade: 'h', nome: 'duração' },
      { cor: COR.chuva, valor: num(e[colunaPico], 1), unidade: 'mm/h', nome: nomePico },
    ]);
  };
  return {
    grid: { left: 52, right: 20, top: 24, bottom: 44 },
    xAxis: eixoValor({
      type: 'log',
      name: 'Duração do evento (h, escala log)',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { fontFamily: FONTE, color: TINTA.texto2, fontSize: 12 },
      min: minimoH,
      axisLine: { show: true, lineStyle: { color: TINTA.regua } },
      axisLabel: { fontFamily: FONTE, color: TINTA.mudo, fontSize: 12, formatter: (v) => num(v, v < 1 ? 2 : 0) },
    }),
    yAxis: eixoValor({
      type: 'log',
      name: 'Intensidade média (mm/h)',
      nameTextStyle: { fontFamily: FONTE, color: TINTA.texto2, fontSize: 12, align: 'left' },
      axisLabel: { fontFamily: FONTE, color: TINTA.mudo, fontSize: 12, formatter: (v) => num(v, v < 0.1 ? 2 : v < 1 ? 1 : 0) },
    }),
    tooltip: { ...dicaBase, trigger: 'item', formatter: dicaEvento },
    animation: false,
    series: [
      {
        name: 'Eventos',
        type: 'scatter',
        data: pontos,
        symbolSize: 9,
        silent: true,
        itemStyle: { color: COR.chuva, opacity: 0.85, borderColor: TINTA.superficie, borderWidth: 2 },
      },
      {
        // Camada invisível maior, só para facilitar o hover (alvo de 24 px)
        name: 'alvo',
        type: 'scatter',
        data: pontos,
        symbolSize: 24,
        itemStyle: { color: 'rgba(0,0,0,0)' },
        emphasis: { itemStyle: { color: 'rgba(42,120,214,0.12)' } },
      },
    ],
  };
}

/* ------------------------------------------------------------------ */
/* Máximas anuais: intensidade × duração (média e faixa entre anos)   */
/* ------------------------------------------------------------------ */

export function opcaoMaximas(maximas) {
  const duracoes = maximas.duracoes_min;
  const anos = maximas.anos.filter((a) => a.cobertura_pct >= 80);
  const base = anos.length ? anos : maximas.anos;
  const porDuracao = duracoes.map((d, i) => base.map((a) => a.valores[i]?.intensidade_mm_h).filter((v) => v !== null));
  const media = porDuracao.map((xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null));
  const minimo = porDuracao.map((xs) => (xs.length ? Math.min(...xs) : null));
  const maximo = porDuracao.map((xs) => (xs.length ? Math.max(...xs) : null));
  const rotulos = duracoes.map((d) => (d < 60 ? `${d} min` : `${d / 60} h`));
  return {
    grid: { left: 52, right: 24, top: 24, bottom: 32 },
    xAxis: eixoCategoria({ data: rotulos, boundaryGap: false }),
    yAxis: eixoValor({ type: 'log', name: 'mm/h (escala log)', nameTextStyle: { fontFamily: FONTE, color: TINTA.texto2, fontSize: 12, align: 'left' } }),
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: ponteiroEixo,
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        return dica(rotulos[i], [
          { cor: COR.chuva, valor: num(media[i], 1), unidade: 'mm/h', nome: `média de ${base.length} ano(s)` },
          { cor: COR.chuva, valor: num(maximo[i], 1), unidade: 'mm/h', nome: 'maior' },
          { cor: COR.chuva, valor: num(minimo[i], 1), unidade: 'mm/h', nome: 'menor' },
        ]);
      },
    },
    animation: false,
    series: [
      { name: 'menor', type: 'line', data: minimo, stack: 'f', symbol: 'none', lineStyle: { opacity: 0 }, silent: true },
      {
        name: 'faixa',
        type: 'line',
        data: maximo.map((v, i) => (v !== null && minimo[i] !== null ? v - minimo[i] : null)),
        stack: 'f',
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { color: COR.chuva, opacity: 0.12 },
        silent: true,
      },
      {
        name: 'Média',
        type: 'line',
        data: media,
        symbolSize: 8,
        lineStyle: { width: 2, color: COR.chuva },
        itemStyle: { color: COR.chuva, borderColor: TINTA.superficie, borderWidth: 2 },
      },
    ],
  };
}

/* ------------------------------------------------------------------ */
/* Balanço hídrico                                                    */
/* ------------------------------------------------------------------ */

function rotuloBH(l, escala) {
  return escala === 'diario' ? dataBR(l.inicio) : mesAno(l.inicio);
}

export function opcaoExtrato(linhas, escala, limites = {}, legenda = true) {
  const categorias = linhas.map((l) => rotuloBH(l, escala));
  return {
    legend: legenda ? { ...legendaBase, data: ['Excedente (EXC)', 'Deficiência (DEF)'] } : undefined,
    grid: { left: 48, right: 16, top: legenda ? 36 : 12, bottom: 32 },
    xAxis: eixoCategoria({ data: categorias }),
    yAxis: eixoValor({
      min: limites.min,
      max: limites.max,
      axisLabel: { fontFamily: FONTE, color: TINTA.mudo, fontSize: 12, formatter: (v) => num(Math.abs(v), 0) },
    }),
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(34,48,58,0.06)' } },
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        const l = linhas[i];
        return dica(categorias[i], [
          { cor: COR.excedente, valor: num(l.exc_mm, 1), unidade: 'mm', nome: 'excedente' },
          { cor: COR.deficiencia, valor: num(l.def_mm, 1), unidade: 'mm', nome: 'deficiência' },
        ]);
      },
    },
    animation: false,
    series: [
      {
        name: 'Excedente (EXC)',
        type: 'bar',
        stack: 'extrato',
        data: linhas.map((l) => l.exc_mm),
        barMaxWidth: 24,
        barMinWidth: 1,
        itemStyle: { color: COR.excedente, borderRadius: [4, 4, 0, 0] },
      },
      {
        name: 'Deficiência (DEF)',
        type: 'bar',
        stack: 'extrato',
        data: linhas.map((l) => -l.def_mm),
        barMaxWidth: 24,
        barMinWidth: 1,
        itemStyle: { color: COR.deficiencia, borderRadius: [0, 0, 4, 4] },
      },
    ],
  };
}

export function opcaoPEtpEtr(linhas, escala) {
  const categorias = linhas.map((l) => rotuloBH(l, escala));
  return {
    legend: { ...legendaBase },
    grid: { left: 48, right: 16, top: 36, bottom: 32 },
    xAxis: eixoCategoria({ data: categorias }),
    yAxis: eixoValor({ min: 0 }),
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: ponteiroEixo,
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        const l = linhas[i];
        return dica(categorias[i], [
          { cor: COR.chuva, valor: num(l.p_mm, 1), unidade: 'mm', nome: 'chuva (P)' },
          { cor: COR.etp, valor: num(l.etp_mm, 1), unidade: 'mm', nome: 'ETP' },
          { cor: COR.etr, valor: num(l.etr_mm, 1), unidade: 'mm', nome: 'ETR' },
        ]);
      },
    },
    animation: false,
    series: [
      {
        name: 'Chuva (P)',
        type: 'bar',
        data: linhas.map((l) => l.p_mm),
        barMaxWidth: 24,
        barMinWidth: 1,
        itemStyle: { color: COR.chuva, opacity: 0.55, borderRadius: [4, 4, 0, 0] },
      },
      {
        name: 'ETP',
        type: 'line',
        data: linhas.map((l) => l.etp_mm),
        showSymbol: false,
        lineStyle: { width: 2, color: COR.etp },
        itemStyle: { color: COR.etp },
      },
      {
        name: 'ETR',
        type: 'line',
        data: linhas.map((l) => l.etr_mm),
        showSymbol: false,
        lineStyle: { width: 2, color: COR.etr },
        itemStyle: { color: COR.etr },
      },
    ],
  };
}

export function opcaoArmazenamento(linhas, escala, cad) {
  const categorias = linhas.map((l) => rotuloBH(l, escala));
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 32 },
    xAxis: eixoCategoria({ data: categorias, boundaryGap: false }),
    yAxis: eixoValor({ min: 0, max: Math.ceil((cad * 1.1) / 10) * 10 }),
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: ponteiroEixo,
      formatter: (ps) => {
        const i = ps[0]?.dataIndex;
        const l = linhas[i];
        return dica(categorias[i], [
          { cor: COR.chuva, valor: num(l.arm_mm, 1), unidade: 'mm', nome: `armazenado (${num((100 * l.arm_mm) / cad, 0)}% da CAD)` },
        ]);
      },
    },
    animation: false,
    series: [
      {
        name: 'Água armazenada (ARM)',
        type: 'line',
        data: linhas.map((l) => l.arm_mm),
        showSymbol: false,
        lineStyle: { width: 2, color: COR.chuva },
        itemStyle: { color: COR.chuva },
        areaStyle: { color: COR.chuva, opacity: 0.1 },
        markLine: {
          symbol: 'none',
          silent: true,
          lineStyle: { color: TINTA.texto2, width: 1, type: 'solid' },
          label: { formatter: `CAD ${num(cad, 0)} mm`, position: 'insideEndTop', color: TINTA.texto2, fontFamily: FONTE, fontSize: 12 },
          data: [{ yAxis: cad }],
        },
      },
    ],
  };
}

/* ------------------------------------------------------------------ */
/* Comparação entre postos                                            */
/* ------------------------------------------------------------------ */

/** Excedente (para cima) e deficiência (para baixo) de cada posto no período. */
export function opcaoDefExcPostos(itens) {
  const categorias = itens.map((x) => x.nome);
  return {
    legend: { ...legendaBase, data: ['Excedente (EXC)', 'Deficiência (DEF)'] },
    grid: { left: 52, right: 16, top: 36, bottom: 40 },
    xAxis: eixoCategoria({ data: categorias, axisLabel: { ...textoBaseCategoria, interval: 0, width: 96, overflow: 'break' } }),
    yAxis: eixoValor({ axisLabel: { fontFamily: FONTE, color: TINTA.mudo, fontSize: 12, formatter: (v) => num(Math.abs(v), 0) } }),
    tooltip: {
      ...dicaBase,
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(34,48,58,0.06)' } },
      formatter: (ps) => {
        const x = itens[ps[0]?.dataIndex];
        if (!x) return '';
        return dica(x.nome, [
          { cor: COR.excedente, valor: num(x.exc, 0), unidade: 'mm', nome: 'excedente' },
          { cor: COR.deficiencia, valor: num(x.def, 0), unidade: 'mm', nome: 'deficiência' },
        ]);
      },
    },
    animation: false,
    series: [
      {
        name: 'Excedente (EXC)',
        type: 'bar',
        stack: 'bh',
        data: itens.map((x) => x.exc),
        barMaxWidth: 40,
        itemStyle: { color: COR.excedente, borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', formatter: (p) => num(p.value, 0), ...textoRotuloBarra },
      },
      {
        name: 'Deficiência (DEF)',
        type: 'bar',
        stack: 'bh',
        data: itens.map((x) => -x.def),
        barMaxWidth: 40,
        itemStyle: { color: COR.deficiencia, borderRadius: [0, 0, 4, 4] },
        label: { show: true, position: 'bottom', formatter: (p) => num(Math.abs(p.value), 0), ...textoRotuloBarra },
      },
    ],
  };
}

const textoBaseCategoria = { fontFamily: FONTE, color: TINTA.mudo, fontSize: 12 };
const textoRotuloBarra = { fontFamily: FONTE, color: TINTA.texto2, fontSize: 12 };

/** Dispersão entre dois postos (mesmos dias ou meses), com a linha 1:1 e a reta de regressão. */
export function opcaoParPostos(par) {
  const pontos = par.x.map((x, i) => [x, par.y[i]]);
  const maximo = Math.max(1, ...par.x, ...par.y);
  const minimo = par.variavel === 'temp_mensal' ? Math.min(...par.x, ...par.y) : 0;
  const passo = par.variavel === 'temp_mensal' ? 1 : maximo > 200 ? 50 : maximo > 50 ? 10 : 5;
  const lim = [Math.floor(minimo / passo) * passo, Math.ceil((maximo * 1.02) / passo) * passo];
  const reg = par.regressao;
  const linhas = [
    { nome: 'Linha 1:1 (valores iguais)', dados: [[lim[0], lim[0]], [lim[1], lim[1]]], estilo: { color: TINTA.regua, type: 'dashed', width: 1.5 } },
  ];
  if (reg) {
    const f = (x) => reg.intercepto + reg.inclinacao * x;
    linhas.push({ nome: 'Reta de regressão', dados: [[lim[0], f(lim[0])], [lim[1], f(lim[1])]], estilo: { color: TINTA.texto, width: 2 } });
  }
  const unidade = par.unidade;
  return {
    legend: { ...legendaBase, data: linhas.map((l) => l.nome), top: 'auto', bottom: 0 },
    grid: { left: 56, right: 20, top: 36, bottom: 84 },
    xAxis: eixoValor({
      min: lim[0],
      max: lim[1],
      name: `${par.a.nome_curto} (${unidade})`,
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: { fontFamily: FONTE, color: TINTA.texto2, fontSize: 12 },
      axisLine: { show: true, lineStyle: { color: TINTA.regua } },
    }),
    yAxis: eixoValor({
      min: lim[0],
      max: lim[1],
      name: `${par.b.nome_curto} (${unidade})`,
      nameTextStyle: { fontFamily: FONTE, color: TINTA.texto2, fontSize: 12, align: 'left' },
    }),
    tooltip: {
      ...dicaBase,
      trigger: 'item',
      formatter: (p) => {
        if (p.seriesName !== 'Pares') return '';
        const t = par.t[p.dataIndex];
        const titulo = par.variavel === 'chuva_diaria' ? dataBR(t) : mesAno(`${t}-01`);
        return dica(titulo, [
          { cor: COR.chuva, valor: num(p.value[0], 1), unidade, nome: par.a.nome_curto },
          { cor: COR.chuva, valor: num(p.value[1], 1), unidade, nome: par.b.nome_curto },
        ]);
      },
    },
    animation: false,
    series: [
      {
        name: 'Pares',
        type: 'scatter',
        data: pontos,
        symbolSize: pontos.length > 2000 ? 5 : 8,
        large: pontos.length > 2000,
        itemStyle: { color: par.variavel === 'temp_mensal' ? COR.temperatura : COR.chuva, opacity: pontos.length > 2000 ? 0.45 : 0.8 },
      },
      ...linhas.map((l) => ({
        name: l.nome,
        type: 'line',
        data: l.dados,
        showSymbol: false,
        silent: true,
        lineStyle: l.estilo,
        itemStyle: { color: l.estilo.color },
      })),
    ],
  };
}
