import { useMemo } from 'react';
import { useApi } from '../api.js';
import { linhasDaSerie } from '../colunas.js';
import Grafico from '../componentes/Grafico.jsx';
import {
  Aviso, BarraPeriodo, BlocoGrafico, Carregando, Ficha, IntroAba, TabelaDobravel,
} from '../componentes/Comuns.jsx';
import { dataBR, dataHoraBR, num, periodoExtenso } from '../formato.js';
import {
  NOME_PASSO, POR_PASSO, opcaoBarrasChuva, opcaoIntensidade, opcaoPluviograma, opcaoTemperatura, opcaoUmidade, opcaoVento,
} from '../graficos/opcoes.js';
import { temDados } from '../graficos/tema.js';
import { textosResolucao, useMeta } from '../meta.jsx';
import { usePeriodo } from '../periodo.js';

const TIPO_TEMPO = { '15min': 'datahora', '1h': 'datahora', '1D': 'data', '1W': 'data', '1M': 'data' };

export default function Painel() {
  const { periodo, escolherPreset, escolherIntervalo, presets } = usePeriodo('30d');
  const { meta, versao, api, posto } = useMeta();
  const textos = textosResolucao(posto?.resolucao_min);

  const params = periodo ? { inicio: periodo.inicio, fim: periodo.fim, v: versao } : null;
  const { dados, erro, carregando } = useApi(`${api}/painel`, params, Boolean(periodo));

  const limites = meta?.limites;
  const paramsAnual = limites?.inicio
    ? { escala: 'anual', inicio: limites.inicio.slice(0, 10), fim: limites.fim.slice(0, 10), v: versao }
    : null;
  const anual = useApi(`${api}/relatorio`, paramsAnual, Boolean(paramsAnual));

  const serie = dados?.serie;
  const passo = dados?.passo;
  const r = dados?.resumo;

  const opcoes = useMemo(() => {
    if (!serie?.t?.length) return null;
    return {
      pluviograma: opcaoPluviograma(serie, passo),
      intensidade: temDados(serie, 'intensidade_max_mm_h') ? opcaoIntensidade(serie, passo, textos.noIntervalo) : null,
      temperatura: temDados(serie, 'temp_c') ? opcaoTemperatura(serie, passo) : null,
      umidade: temDados(serie, 'ur_pct') ? opcaoUmidade(serie, passo) : null,
      vento: temDados(serie, 'vento_ms') ? opcaoVento(serie, passo) : null,
    };
  }, [serie, passo, textos.noIntervalo]);

  const opcaoAnual = useMemo(
    () => (anual.dados?.linhas?.length ? opcaoBarrasChuva(anual.dados.linhas, undefined, undefined, undefined, anoIncompleto) : null),
    [anual.dados],
  );

  const colTempo = { chave: 't', rotulo: passo === '1M' ? 'Mês' : passo === '1W' ? 'Semana até' : 'Data', tipo: TIPO_TEMPO[passo] };

  return (
    <div className="pagina">
      <IntroAba titulo="Painel">
        {posto && !posto.tem_registros
          ? 'Chuva diária e acumulada, temperatura, umidade e vento deste posto, a partir dos totais diários.'
          : `Chuva por intervalo e acumulada, intensidade, temperatura, umidade e vento medidos ${
              posto?.resolucao_min === 60 ? 'a cada hora' : 'a cada 15 minutos'
            } neste posto.`}
      </IntroAba>

      <BarraPeriodo
        periodo={periodo}
        presets={presets}
        escolherPreset={escolherPreset}
        escolherIntervalo={escolherIntervalo}
      />

      {erro && (
        <Aviso tipo="erro" titulo="Não foi possível carregar o painel">
          {erro.message}
        </Aviso>
      )}
      {!dados && !erro && <Carregando texto="Carregando os dados da estação…" />}

      {dados && (
        <div className={carregando ? 'esmaecido' : undefined}>
          {!serie?.t?.length ? (
            <Aviso tipo="info" titulo="Sem registros neste período">
              Escolha outro período: os dados vão de {dataBR(limites?.inicio)} a {dataBR(limites?.fim)}.
            </Aviso>
          ) : (
            <>
              <section className="pluviograma" aria-labelledby="titulo-pluviograma">
                <h2 id="titulo-pluviograma" className="pluviograma__titulo">
                  {periodoExtenso(periodo.inicio, periodo.fim)}
                </h2>
                <Grafico
                  opcao={opcoes.pluviograma}
                  altura={440}
                  descricao={`Chuva ${POR_PASSO[passo]} e chuva acumulada: ${num(r.chuva_total_mm, 1)} mm no período.`}
                />
                <TabelaDobravel
                  legenda="Chuva por intervalo e acumulada"
                  colunas={[
                    colTempo,
                    { chave: 'chuva_mm', rotulo: `Chuva ${POR_PASSO[passo]} (mm)`, tipo: 'num', casas: 1 },
                    { chave: 'chuva_acum_mm', rotulo: 'Acumulada (mm)', tipo: 'num', casas: 1 },
                  ]}
                  linhas={linhasDaSerie(serie, ['chuva_mm', 'chuva_acum_mm'])}
                />
              </section>

              <Ficha itens={itensFicha(r, textos)} />

              {r.variaveis.length === 1 && (
                <Aviso tipo="info" titulo="Só há chuva neste período">
                  Temperatura, umidade e vento aparecem aqui quando a série do posto tiver essas medidas.
                </Aviso>
              )}

              <div className="multiplos">
                {opcoes.intensidade && (
                  <BlocoGrafico
                    titulo="Intensidade da chuva"
                    nota={
                      (passo === '15min' && posto?.resolucao_min !== 60) || (passo === '1h' && posto?.resolucao_min === 60)
                        ? `Intensidade de cada intervalo de ${textos.intervalo} (mm/h)`
                        : `Maior intensidade ${textos.noIntervalo} dentro de cada ${NOME_PASSO[passo]} (mm/h)`
                    }
                  >
                    <Grafico opcao={opcoes.intensidade} altura={220} descricao="Intensidade máxima da chuva em mm/h" />
                    <TabelaDobravel
                      legenda="Intensidade máxima"
                      colunas={[colTempo, { chave: 'intensidade_max_mm_h', rotulo: 'Intensidade máx. (mm/h)', tipo: 'num', casas: 1 }]}
                      linhas={linhasDaSerie(serie, ['intensidade_max_mm_h'])}
                    />
                  </BlocoGrafico>
                )}
                {opcoes.temperatura && (
                  <BlocoGrafico titulo="Temperatura do ar" nota="Média (linha) e faixa entre a mínima e a máxima (área), em °C">
                    <Grafico opcao={opcoes.temperatura} altura={220} descricao="Temperatura do ar" />
                    <TabelaDobravel
                      legenda="Temperatura"
                      colunas={[
                        colTempo,
                        { chave: 'temp_c', rotulo: 'Média (°C)', tipo: 'num', casas: 1 },
                        { chave: 'temp_max_c', rotulo: 'Máx. (°C)', tipo: 'num', casas: 1 },
                        { chave: 'temp_min_c', rotulo: 'Mín. (°C)', tipo: 'num', casas: 1 },
                      ]}
                      linhas={linhasDaSerie(serie, ['temp_c', 'temp_max_c', 'temp_min_c'])}
                    />
                  </BlocoGrafico>
                )}
                {opcoes.umidade && (
                  <BlocoGrafico titulo="Umidade relativa do ar" nota="Média de cada intervalo (%)">
                    <Grafico opcao={opcoes.umidade} altura={220} descricao="Umidade relativa do ar" />
                    <TabelaDobravel
                      legenda="Umidade relativa"
                      colunas={[colTempo, { chave: 'ur_pct', rotulo: 'Umidade (%)', tipo: 'num', casas: 0 }]}
                      linhas={linhasDaSerie(serie, ['ur_pct'])}
                    />
                  </BlocoGrafico>
                )}
                {opcoes.vento && (
                  <BlocoGrafico titulo="Velocidade do vento" nota="Média e rajada máxima de cada intervalo (m/s)">
                    <Grafico opcao={opcoes.vento} altura={240} descricao="Velocidade do vento" />
                    <TabelaDobravel
                      legenda="Vento"
                      colunas={[
                        colTempo,
                        { chave: 'vento_ms', rotulo: 'Média (m/s)', tipo: 'num', casas: 1 },
                        { chave: 'vento_max_ms', rotulo: 'Rajada (m/s)', tipo: 'num', casas: 1 },
                      ]}
                      linhas={linhasDaSerie(serie, ['vento_ms', 'vento_max_ms'])}
                    />
                  </BlocoGrafico>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {opcaoAnual && (
        <BlocoGrafico
          titulo="Chuva por ano"
          nota="Total de cada ano. Barras claras: anos com dados em menos de 90% dos dias, como o ano em curso."
          carregando={anual.carregando}
        >
          <Grafico opcao={opcaoAnual} altura={260} descricao="Chuva total por ano" />
          <TabelaDobravel
            legenda="Chuva por ano"
            colunas={[
              { chave: 'periodo', rotulo: 'Ano', tipo: 'texto' },
              { chave: 'chuva_mm', rotulo: 'Chuva (mm)', tipo: 'num', casas: 1 },
              { chave: 'dias_chuva', rotulo: 'Dias com chuva', tipo: 'num', casas: 0 },
              { chave: 'chuva_max_diaria_mm', rotulo: 'Maior chuva diária (mm)', tipo: 'num', casas: 1 },
              { chave: 'dias_com_dados', rotulo: 'Dias com dados', tipo: 'num', casas: 0 },
            ]}
            linhas={anual.dados.linhas}
          />
        </BlocoGrafico>
      )}
    </div>
  );
}

function anoIncompleto(l) {
  const ano = Number(l.periodo);
  const dias = (Date.UTC(ano + 1, 0, 1) - Date.UTC(ano, 0, 1)) / 86400000;
  return l.dias_com_dados < 0.9 * dias;
}

function itensFicha(r, textos) {
  const soDiario = r.resolucao_min === 1440;
  const itens = [
    { rotulo: 'Chuva total', valor: num(r.chuva_total_mm, 1), unidade: 'mm' },
    { rotulo: 'Dias com chuva (≥ 1 mm)', valor: String(r.dias_chuva), nota: `em ${r.periodo.dias} dias` },
    {
      rotulo: 'Maior chuva em um dia',
      valor: num(r.chuva_max_diaria.valor, 1),
      unidade: 'mm',
      nota: r.chuva_max_diaria.quando ? `em ${dataBR(r.chuva_max_diaria.quando)}` : null,
    },
    !soDiario && {
      rotulo: textos.maiorIntensidade,
      valor: num(r.intensidade_max.valor, 1),
      unidade: 'mm/h',
      nota: r.intensidade_max.quando && r.intensidade_max.valor > 0 ? `às ${dataHoraBR(r.intensidade_max.quando)}` : null,
    },
  ];
  if (r.temp_media_c !== null) {
    itens.push({
      rotulo: 'Temperatura média',
      valor: num(r.temp_media_c, 1),
      unidade: '°C',
      nota: r.temp_max.valor !== null ? `máx. ${num(r.temp_max.valor, 1)} °C, mín. ${num(r.temp_min.valor, 1)} °C` : null,
    });
  }
  if (r.ur_media_pct !== null) itens.push({ rotulo: 'Umidade relativa média', valor: num(r.ur_media_pct, 0), unidade: '%' });
  if (r.vento_medio_ms !== null) {
    itens.push({
      rotulo: 'Vento médio',
      valor: num(r.vento_medio_ms, 1),
      unidade: 'm/s',
      nota:
        r.rajada_max.valor !== null
          ? `rajada de ${num(r.rajada_max.valor, 1)} m/s em ${(soDiario ? dataBR : dataHoraBR)(r.rajada_max.quando)}`
          : r.vento_max_15min?.valor !== null && r.vento_max_15min?.valor !== undefined
            ? `máx. de ${num(r.vento_max_15min.valor, 1)} m/s (média ${textos.noIntervalo}) em ${dataHoraBR(r.vento_max_15min.quando)}`
            : null,
    });
  }
  itens.push({
    rotulo: 'Dados válidos',
    valor: num(r.cobertura_pct, 1),
    unidade: '%',
    nota: soDiario ? `${num(r.registros, 0)} dias com dados` : `${num(r.registros, 0)} ${textos.registros}`,
  });
  return itens;
}
