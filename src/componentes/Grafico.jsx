import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  AriaComponent,
  AxisPointerComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import localePtBr from '../graficos/locale-ptbr.js';
import { reduzMovimento } from '../graficos/tema.js';

echarts.use([
  BarChart, LineChart, ScatterChart, GridComponent, TooltipComponent, AxisPointerComponent,
  LegendComponent, MarkLineComponent, GraphicComponent, AriaComponent, CanvasRenderer,
]);
echarts.registerLocale('PT-br', localePtBr);

/**
 * Gráfico ECharts responsivo. `descricao` vira o nome acessível do gráfico;
 * os valores ficam acessíveis pela tabela ao lado (componente TabelaDobravel).
 */
export default function Grafico({ opcao, altura = 300, descricao, aoClicar }) {
  const elemento = useRef(null);
  const instancia = useRef(null);

  useEffect(() => {
    const grafico = echarts.init(elemento.current, null, { renderer: 'canvas', locale: 'PT-br' });
    instancia.current = grafico;
    const observador = new ResizeObserver(() => grafico.resize());
    observador.observe(elemento.current);
    return () => {
      observador.disconnect();
      grafico.dispose();
      instancia.current = null;
    };
  }, []);

  useEffect(() => {
    const grafico = instancia.current;
    if (!grafico || !opcao) return;
    const animar = !reduzMovimento() && opcao.animation !== false;
    grafico.setOption({ ...opcao, animation: animar, aria: { enabled: true } }, { notMerge: true });
  }, [opcao]);

  useEffect(() => {
    const grafico = instancia.current;
    if (!grafico || !aoClicar) return undefined;
    grafico.on('click', aoClicar);
    return () => grafico.off('click', aoClicar);
  }, [aoClicar]);

  return <div ref={elemento} className="grafico__area" style={{ height: altura }} role="img" aria-label={descricao} />;
}
