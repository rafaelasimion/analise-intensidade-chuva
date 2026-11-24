import { useMemo, useState } from 'react';
import { useApi } from '../api.js';
import Grafico from '../componentes/Grafico.jsx';
import {
  Aviso, BarraPeriodo, BlocoGrafico, CampoNumero, Carregando, IntroAba, Segmentado, Tabela, TabelaDobravel,
} from '../componentes/Comuns.jsx';
import Downloads from '../componentes/Downloads.jsx';
import { dataBR, num } from '../formato.js';
import { opcaoEventos, opcaoMaximas } from '../graficos/opcoes.js';
import { useMeta } from '../meta.jsx';
import { usePeriodo } from '../periodo.js';

const ordens = (horario) => [
  { id: 'inicio', rotulo: 'Data' },
  { id: 'chuva_mm', rotulo: 'Chuva' },
  horario ? { id: 'i60_mm_h', rotulo: 'Pico (I60)' } : { id: 'i15_mm_h', rotulo: 'Pico (I15)' },
  { id: 'duracao_min', rotulo: 'Duração' },
];

const JANELA = { i15_mm_h: 'em 15 min', i30_mm_h: 'em 30 min', i60_mm_h: 'em 1 h', intensidade_media_mm_h: 'de média' };

const COLUNAS_EVENTOS = [
  { chave: 'evento', rotulo: 'Nº', tipo: 'num', casas: 0 },
  { chave: 'inicio', rotulo: 'Início', tipo: 'datahora' },
  { chave: 'fim', rotulo: 'Fim', tipo: 'datahora' },
  { chave: 'duracao_min', rotulo: 'Duração', tipo: 'duracao' },
  { chave: 'chuva_mm', rotulo: 'Chuva (mm)', tipo: 'num', casas: 1 },
  { chave: 'intensidade_media_mm_h', rotulo: 'Intensidade média (mm/h)', tipo: 'num', casas: 1 },
  { chave: 'i15_mm_h', rotulo: 'I15 (mm/h)', tipo: 'num', casas: 1 },
  { chave: 'i30_mm_h', rotulo: 'I30 (mm/h)', tipo: 'num', casas: 1 },
  { chave: 'i60_mm_h', rotulo: 'I60 (mm/h)', tipo: 'num', casas: 1 },
];

export default function Eventos() {
  const { periodo, escolherPreset, escolherIntervalo, presets } = usePeriodo('ano');
  const { versao, api, posto } = useMeta();
  const horario = posto?.resolucao_min === 60;
  const semRegistros = posto && !posto.tem_registros;
  const [seco, setSeco] = useState(6);
  const [minimo, setMinimo] = useState(1);
  const [ordem, setOrdem] = useState('inicio');

  const base = periodo && !semRegistros ? { inicio: periodo.inicio, fim: periodo.fim, v: versao } : null;
  const ev = useApi(`${api}/eventos`, base && { ...base, intervalo_seco_h: seco, chuva_min_mm: minimo }, Boolean(base));
  const mx = useApi(`${api}/maximas`, base, Boolean(base));
  const colunaPico = horario ? 'i60_mm_h' : 'i15_mm_h';
  const colunasEventos = COLUNAS_EVENTOS.filter((c) => !horario || !['i15_mm_h', 'i30_mm_h'].includes(c.chave));

  const eventos = ev.dados?.eventos ?? [];
  const ordenados = useMemo(() => {
    const copia = [...eventos];
    if (ordem === 'inicio') return copia;
    return copia.sort((a, b) => (b[ordem] ?? -1) - (a[ordem] ?? -1));
  }, [eventos, ordem]);
  const opcaoDispersao = useMemo(
    () => (eventos.length ? opcaoEventos(eventos, colunaPico, horario ? 'pico em 1 h' : 'pico em 15 min') : null),
    [eventos, colunaPico, horario],
  );
  const opcaoMax = useMemo(() => (mx.dados?.anos?.length ? opcaoMaximas(mx.dados) : null), [mx.dados]);
  const resumo = ev.dados?.resumo;

  return (
    <div className="pagina">
      <IntroAba titulo="Eventos de chuva">
        Cada chuva separada das outras por um período seco, com a duração, o total e a intensidade em mm/h.
        {horario && ' Nas estações horárias a menor janela de intensidade é de 1 hora (I60).'}
      </IntroAba>

      {semRegistros && (
        <Aviso tipo="info" titulo="Eventos precisam dos dados horários">
          Este posto ainda só tem totais diários no site. Os eventos e as máximas aparecem depois da próxima atualização
          automática.
        </Aviso>
      )}

      <BarraPeriodo periodo={periodo} presets={presets} escolherPreset={escolherPreset} escolherIntervalo={escolherIntervalo}>
        <CampoNumero rotulo="Período seco entre eventos" unidade="h" valor={seco} aoMudar={setSeco} min={0.25} max={72} />
        <CampoNumero rotulo="Chuva mínima do evento" unidade="mm" valor={minimo} aoMudar={setMinimo} min={0} max={500} />
      </BarraPeriodo>

      {ev.erro && (
        <Aviso tipo="erro" titulo="Não foi possível separar os eventos">
          {ev.erro.message}
        </Aviso>
      )}
      {!ev.dados && !ev.erro && <Carregando />}

      {ev.dados && (
        <div className={ev.carregando ? 'esmaecido' : undefined}>
          <p className="frase-resumo">
            {resumo.n_eventos === 0
              ? 'Nenhum evento com esses critérios no período.'
              : `${num(resumo.n_eventos, 0)} eventos somando ${num(resumo.chuva_total_eventos_mm, 1)} mm, com duração média de ${num(resumo.duracao_media_min / 60, 1)} h. ` +
                `O maior foi o nº ${resumo.maior_evento.evento} (${num(resumo.maior_evento.chuva_mm, 1)} mm, ${dataBR(resumo.maior_evento.inicio)}); ` +
                `o mais intenso, o nº ${resumo.mais_intenso.evento} (${num(resumo.mais_intenso.intensidade_mm_h, 1)} mm/h ${JANELA[resumo.mais_intenso.coluna] ?? ''}, ${dataBR(resumo.mais_intenso.inicio)}).`}
          </p>

          {opcaoDispersao && (
            <BlocoGrafico
              titulo="Duração e intensidade média dos eventos"
              nota="Cada ponto é um evento. Chuvas curtas tendem a ser mais intensas; os valores de cada ponto estão na tabela abaixo."
            >
              <Grafico opcao={opcaoDispersao} altura={340} descricao="Dispersão entre duração e intensidade média dos eventos de chuva" />
            </BlocoGrafico>
          )}

          {eventos.length > 0 && (
            <section className="secao" aria-labelledby="titulo-eventos">
              <div className="secao__topo">
                <h2 id="titulo-eventos" className="secao__titulo">Tabela de eventos</h2>
                <Segmentado rotulo="Ordenar por" opcoes={ordens(horario)} valor={ordem} aoMudar={setOrdem} />
              </div>
              <Tabela legenda="Eventos de chuva" colunas={colunasEventos} linhas={ordenados.map((e) => ({ ...e, id: e.evento }))} />
              <Downloads
                caminho={`${api}/download`}
                params={{ tipo: 'eventos', inicio: periodo.inicio, fim: periodo.fim, intervalo_seco_h: seco, chuva_min_mm: minimo }}
                variavelR="eventos"
              />
            </section>
          )}
        </div>
      )}

      <Calculadora />

      <section className="secao" aria-labelledby="titulo-maximas">
        <h2 id="titulo-maximas" className="secao__titulo">Máximas anuais por duração</h2>
        <p className="secao__texto">
          A maior chuva de cada ano em janelas móveis de {horario ? '1 hora' : '15 minutos'} a 24 horas, base para curvas
          intensidade-duração-frequência (IDF). Anos com menos de 80% de dados ficam fora da média.
        </p>
        {mx.erro && <Aviso tipo="erro">{mx.erro.message}</Aviso>}
        {mx.dados && mx.dados.anos.length > 0 && (
          <div className={mx.carregando ? 'esmaecido' : undefined}>
            {opcaoMax && (
              <BlocoGrafico titulo="Intensidade máxima × duração" nota="Média dos anos (linha) e faixa entre o menor e o maior valor anual (área)">
                <Grafico opcao={opcaoMax} altura={300} descricao="Intensidade máxima anual por duração" />
              </BlocoGrafico>
            )}
            <TabelaMaximas maximas={mx.dados} />
            <Downloads
              caminho={`${api}/download`}
              params={{ tipo: 'maximas', inicio: periodo.inicio, fim: periodo.fim }}
              variavelR="maximas"
            />
          </div>
        )}
      </section>
    </div>
  );
}

function TabelaMaximas({ maximas }) {
  const [grandeza, setGrandeza] = useState('intensidade_mm_h');
  const rot = (d) => (d < 60 ? `${d} min` : `${d / 60} h`);
  const colunas = [
    { chave: 'ano', rotulo: 'Ano', tipo: 'texto' },
    { chave: 'cobertura_pct', rotulo: 'Dados (%)', tipo: 'num', casas: 0 },
    ...maximas.duracoes_min.map((d, i) => ({
      chave: `d${i}`,
      rotulo: rot(d),
      tipo: 'num',
      casas: 1,
    })),
    { chave: 'chuva_max_dia_mm', rotulo: 'Maior chuva em 1 dia (mm)', tipo: 'num', casas: 1 },
  ];
  const linhas = maximas.anos.map((a) => {
    const l = { id: a.ano, ano: String(a.ano), cobertura_pct: a.cobertura_pct, chuva_max_dia_mm: a.chuva_max_dia_mm };
    a.valores.forEach((v, i) => {
      l[`d${i}`] = v[grandeza];
    });
    return l;
  });
  return (
    <>
      <div className="secao__topo">
        <Segmentado
          rotulo="Mostrar"
          opcoes={[
            { id: 'intensidade_mm_h', rotulo: 'Intensidade (mm/h)' },
            { id: 'chuva_mm', rotulo: 'Chuva (mm)' },
          ]}
          valor={grandeza}
          aoMudar={setGrandeza}
        />
      </div>
      <Tabela legenda="Máximas anuais por duração" colunas={colunas} linhas={linhas} />
      {maximas.estatisticas?.length > 0 && (
        <TabelaDobravel
          titulo="Média e desvio padrão das máximas (mm/h)"
          legenda="Estatísticas das máximas anuais"
          colunas={[
            { chave: 'rotulo', rotulo: 'Duração', tipo: 'texto' },
            { chave: 'n_anos', rotulo: 'Anos', tipo: 'num', casas: 0 },
            { chave: 'media_mm_h', rotulo: 'Média (mm/h)', tipo: 'num', casas: 1 },
            { chave: 'desvio_padrao_mm_h', rotulo: 'Desvio padrão (mm/h)', tipo: 'num', casas: 1 },
            { chave: 'maxima_mm_h', rotulo: 'Maior (mm/h)', tipo: 'num', casas: 1 },
          ]}
          linhas={maximas.estatisticas.map((e) => ({ ...e, id: e.duracao_min, rotulo: rot(e.duracao_min) }))}
        />
      )}
    </>
  );
}

function Calculadora() {
  const [chuva, setChuva] = useState(25);
  const [minutos, setMinutos] = useState(30);
  const intensidade = minutos > 0 ? chuva / (minutos / 60) : null;
  return (
    <section className="secao calculadora" aria-labelledby="titulo-calculadora">
      <h2 id="titulo-calculadora" className="secao__titulo">Calculadora de intensidade</h2>
      <p className="secao__texto">Para uma chuva medida em campo: intensidade (mm/h) = chuva (mm) ÷ duração (h).</p>
      <div className="calculadora__linha">
        <CampoNumero rotulo="Chuva" unidade="mm" valor={chuva} aoMudar={setChuva} min={0} />
        <CampoNumero rotulo="Duração" unidade="min" valor={minutos} aoMudar={setMinutos} min={1} />
        <output className="calculadora__resultado" aria-live="polite">
          <span className="calculadora__valor">{num(intensidade, 1)}</span>
          <span className="calculadora__unidade">mm/h</span>
        </output>
      </div>
      <p className="texto-pequeno">
        {intensidade !== null && `${num(chuva, 1)} mm em ${num(minutos, 0)} min equivalem a ${num(intensidade, 1)} mm por hora.`}
        {' '}Com dados do posto, use a tabela de eventos acima: ela já traz a duração e a intensidade de cada chuva.
      </p>
    </section>
  );
}
