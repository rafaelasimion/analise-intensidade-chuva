import { useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { urlApi, useApi } from '../api.js';
import { colunasDe } from '../colunas.js';
import Grafico from '../componentes/Grafico.jsx';
import {
  Aviso, BarraPeriodo, BlocoGrafico, CabecalhoPagina, Carregando, Ficha, Segmentado, Tabela,
} from '../componentes/Comuns.jsx';
import Downloads from '../componentes/Downloads.jsx';
import { dataBR, dataHoraBR, num, periodoExtenso } from '../formato.js';
import { opcaoBarrasChuva } from '../graficos/opcoes.js';
import { useMeta } from '../meta.jsx';
import { usePeriodo } from '../periodo.js';

const ESCALAS = [
  { id: 'diario', rotulo: 'Diário' },
  { id: 'semanal', rotulo: 'Semanal' },
  { id: 'mensal', rotulo: 'Mensal' },
  { id: 'anual', rotulo: 'Anual' },
];
const NOME = { diario: 'diário', semanal: 'semanal', mensal: 'mensal', anual: 'anual' };
const UNIDADE = { diario: 'dia', semanal: 'semana', mensal: 'mês', anual: 'ano' };

export default function Relatorios() {
  const { periodo, escolherPreset, escolherIntervalo, presets } = usePeriodo('ano');
  const { meta, versao } = useMeta();
  const [params, setParams] = useSearchParams();
  const escala = params.get('escala') ?? 'mensal';
  const mudarEscala = (id) =>
    setParams((atual) => {
      const novo = new URLSearchParams(atual);
      novo.set('escala', id);
      return novo;
    });

  const consulta = periodo ? { inicio: periodo.inicio, fim: periodo.fim, escala, v: versao } : null;
  const { dados, erro, carregando } = useApi('/api/esalq/relatorio', consulta, Boolean(consulta));
  const r = dados?.resumo;

  const colunas = useMemo(() => {
    if (!dados?.colunas) return [];
    const ocultas = new Set(['inicio', 'fim', 'dias_com_dados']);
    if (escala === 'diario') ocultas.add('momento_intensidade_max');
    return colunasDe(
      dados.colunas.filter((c) => !ocultas.has(c)),
      {
        periodo: { rotulo: UNIDADE[escala][0].toUpperCase() + UNIDADE[escala].slice(1) },
        momento_intensidade_max: { rotulo: 'Quando (intensidade)', tipo: 'datahora' },
      },
    );
  }, [dados?.colunas, escala]);

  const totais = r && {
    periodo: 'Período todo',
    chuva_mm: r.chuva_total_mm,
    dias_chuva: r.dias_chuva,
    chuva_max_diaria_mm: r.chuva_max_diaria.valor,
    data_chuva_max_diaria: r.chuva_max_diaria.quando,
    intensidade_max_mm_h: r.intensidade_max.valor,
    momento_intensidade_max: r.intensidade_max.quando,
    temp_c: r.temp_media_c,
    temp_max_c: r.temp_max.valor,
    temp_min_c: r.temp_min.valor,
    ur_pct: r.ur_media_pct,
    vento_ms: r.vento_medio_ms,
    vento_max_ms: r.rajada_max.valor,
    rad_mj_m2: r.rad_media_mj_m2_dia,
    cobertura_pct: r.cobertura_pct,
  };

  const opcao = useMemo(() => {
    if (!dados?.linhas?.length || dados.linhas.length > 400) return null;
    return opcaoBarrasChuva(dados.linhas);
  }, [dados?.linhas]);

  const est = meta?.estacao;
  const urlPlanilha = periodo ? urlApi('/api/esalq/planilha', { inicio: periodo.inicio, fim: periodo.fim }) : null;

  return (
    <div className="pagina">
      <CabecalhoPagina titulo="Relatórios">
        Resumo diário, semanal, mensal ou anual do período escolhido. O botão de impressão gera uma versão limpa, pronta
        para salvar em PDF.
      </CabecalhoPagina>

      <BarraPeriodo periodo={periodo} presets={presets} escolherPreset={escolherPreset} escolherIntervalo={escolherIntervalo}>
        <Segmentado rotulo="Escala do relatório" opcoes={ESCALAS} valor={escala} aoMudar={mudarEscala} />
      </BarraPeriodo>

      {periodo && (
        <section className="secao nao-imprimir" aria-labelledby="titulo-exportar">
          <h2 id="titulo-exportar" className="secao__titulo">Exportar</h2>
          <Downloads caminho="/api/esalq/download" params={{ tipo: escala, inicio: periodo.inicio, fim: periodo.fim }} variavelR="relatorio">
            <button type="button" className="botao" onClick={() => window.print()}>
              Imprimir ou salvar PDF
            </button>
            <a className="botao" href={urlPlanilha} download>
              Planilha hidrológica completa
            </a>
          </Downloads>
          <p className="texto-pequeno">
            A planilha hidrológica reúne, em abas, os dados de 15 min, os resumos diário, semanal, mensal e anual, os
            eventos de chuva, as máximas anuais e, quando houver temperatura, o balanço hídrico.
          </p>
        </section>
      )}

      {erro && (
        <Aviso tipo="erro" titulo="Não foi possível gerar o relatório">
          {erro.message}
        </Aviso>
      )}
      {!dados && !erro && <Carregando />}

      {dados && r && (
        <article className={`relatorio${carregando ? ' esmaecido' : ''}`} aria-labelledby="titulo-relatorio">
          <header className="relatorio__cabecalho">
            <h2 id="titulo-relatorio" className="relatorio__titulo">
              Relatório {NOME[escala]}: {periodoExtenso(periodo.inicio, periodo.fim)}
            </h2>
            <p className="relatorio__meta">
              {est ? `${est.nome}, ${est.municipio}/SP (lat. ${num(est.lat, 4)}, long. ${num(est.lon, 4)}, ${num(est.alt, 0)} m). ` : ''}
              Registros de {dataHoraBR(r.periodo.primeiro_registro)} a {dataHoraBR(r.periodo.ultimo_registro)}. Gerado em{' '}
              {dataHoraBR(new Date())}.
            </p>
          </header>

          <Ficha
            itens={[
              { rotulo: 'Chuva total', valor: num(r.chuva_total_mm, 1), unidade: 'mm' },
              { rotulo: 'Dias com chuva (≥ 1 mm)', valor: String(r.dias_chuva) },
              {
                rotulo: 'Maior chuva em um dia',
                valor: num(r.chuva_max_diaria.valor, 1),
                unidade: 'mm',
                nota: r.chuva_max_diaria.quando ? dataBR(r.chuva_max_diaria.quando) : null,
              },
              {
                rotulo: 'Maior intensidade (15 min)',
                valor: num(r.intensidade_max.valor, 1),
                unidade: 'mm/h',
                nota: r.intensidade_max.valor > 0 ? dataHoraBR(r.intensidade_max.quando) : null,
              },
              r.temp_media_c !== null && { rotulo: 'Temperatura média', valor: num(r.temp_media_c, 1), unidade: '°C' },
              r.vento_medio_ms !== null && {
                rotulo: 'Vento médio',
                valor: num(r.vento_medio_ms, 1),
                unidade: 'm/s',
                nota: r.rajada_max.valor !== null
                  ? `rajada de ${num(r.rajada_max.valor, 1)} m/s`
                  : `máx. de ${num(r.vento_max_15min.valor, 1)} m/s (média de 15 min)`,
              },
              { rotulo: 'Dados válidos', valor: num(r.cobertura_pct, 1), unidade: '%' },
            ]}
          />

          {opcao && (
            <BlocoGrafico titulo={`Chuva por ${UNIDADE[escala]}`}>
              <Grafico opcao={opcao} altura={240} descricao={`Chuva por ${UNIDADE[escala]} no período`} />
            </BlocoGrafico>
          )}

          <Tabela legenda={`Relatório ${NOME[escala]}`} colunas={colunas} linhas={dados.linhas} rodape={totais} />

          <p className="relatorio__notas">
            Dia com chuva: ≥ 1 mm. Cada registro de 15 min representa o intervalo que termina no horário indicado (o de
            00:00 pertence ao dia anterior). Intensidade = chuva do intervalo ÷ duração. Fonte: estação automática do
            LEB/ESALQ/USP.
          </p>
        </article>
      )}
    </div>
  );
}
