import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { useApi } from '../api.js';
import Grafico from '../componentes/Grafico.jsx';
import {
  Aviso, BlocoGrafico, CabecalhoPagina, Campo, CampoNumero, Carregando, Ficha, Segmentado, Tabela,
} from '../componentes/Comuns.jsx';
import Downloads from '../componentes/Downloads.jsx';
import { mesAno, num, paraData } from '../formato.js';
import { opcaoArmazenamento, opcaoExtrato, opcaoPEtpEtr } from '../graficos/opcoes.js';

const PRESETS = [
  { id: '1m', rotulo: '1 mês', meses: 1 },
  { id: '1a', rotulo: '1 ano', meses: 12 },
  { id: '5a', rotulo: '5 anos', meses: 60 },
  { id: '10a', rotulo: '10 anos', meses: 120 },
  { id: '20a', rotulo: '20 anos', meses: 240 },
  { id: 'outro', rotulo: 'Personalizado' },
];

const COLUNAS_BH = [
  { chave: 'periodo', rotulo: 'Período', tipo: 'texto' },
  { chave: 'p_mm', rotulo: 'P (mm)', tipo: 'num', casas: 1 },
  { chave: 't_c', rotulo: 'T (°C)', tipo: 'num', casas: 1 },
  { chave: 'etp_mm', rotulo: 'ETP', tipo: 'num', casas: 1 },
  { chave: 'p_etp_mm', rotulo: 'P − ETP', tipo: 'num', casas: 1 },
  { chave: 'neg_ac_mm', rotulo: 'NEG.AC', tipo: 'num', casas: 1 },
  { chave: 'arm_mm', rotulo: 'ARM', tipo: 'num', casas: 1 },
  { chave: 'alt_mm', rotulo: 'ALT', tipo: 'num', casas: 1 },
  { chave: 'etr_mm', rotulo: 'ETR', tipo: 'num', casas: 1 },
  { chave: 'def_mm', rotulo: 'DEF', tipo: 'num', casas: 1 },
  { chave: 'exc_mm', rotulo: 'EXC', tipo: 'num', casas: 1 },
];

const NOMES_MES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

function somarMeses(aaaamm, n) {
  const [a, m] = aaaamm.split('-').map(Number);
  const d = new Date(a, m - 1 + n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** Último mês completo de uma série que termina em `fimIso` (ou antes de hoje). */
function ultimoMesCompleto(fimIso) {
  const hoje = new Date();
  let d = fimIso ? paraData(fimIso) : new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate() - 7);
  const ultimoDia = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  if (d.getDate() < ultimoDia) d = new Date(d.getFullYear(), d.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export default function Balanco() {
  const [params, setParams] = useSearchParams();
  const postos = useApi('/api/postos', {});
  const lista = postos.dados?.postos ?? [];

  const codigo = params.get('posto') ?? 'ESALQ';
  const coordenadas = codigo === 'COORD';
  const usarNasa = coordenadas || params.get('dados') === 'nasa';
  const preset = params.get('periodo') ?? '1a';
  const cad = Number(params.get('cad') ?? 100);
  const lat = params.get('lat') ?? '-22.7';
  const lon = params.get('lon') ?? '-47.63';
  const posto = lista.find((p) => p.codigo === codigo);

  const fimRef = ultimoMesCompleto(usarNasa ? null : posto?.fim_dados);
  const p = PRESETS.find((x) => x.id === preset);
  const inicio = preset === 'outro' ? params.get('inicio') ?? somarMeses(fimRef, -11) : somarMeses(fimRef, -((p?.meses ?? 12) - 1));
  const fim = preset === 'outro' ? params.get('fim') ?? fimRef : fimRef;
  const escala = params.get('escala') ?? (preset === '1m' ? 'diario' : 'mensal');

  const mudar = (mudancas) =>
    setParams((atual) => {
      const novo = new URLSearchParams(atual);
      for (const [k, v] of Object.entries(mudancas)) {
        if (v === null || v === undefined) novo.delete(k);
        else novo.set(k, String(v));
      }
      return novo;
    });

  const fonte = usarNasa ? 'nasa' : codigo === 'ESALQ' ? 'esalq' : 'inmet';
  const pronto = coordenadas || Boolean(posto);
  const consulta = pronto
    ? {
        fonte,
        codigo: coordenadas ? undefined : codigo,
        lat: coordenadas ? lat : undefined,
        lon: coordenadas ? lon : undefined,
        inicio,
        fim,
        cad,
        escala,
      }
    : null;
  const bh = useApi('/api/balanco', consulta, Boolean(consulta));
  const d = bh.dados;

  const seq = d?.sequencial ?? [];
  const resumoMensal = escala === 'diario' ? d?.sequencial_mensal ?? [] : seq;
  const graficoLinhas = escala === 'diario' && seq.length > 400 ? resumoMensal : seq;
  const graficoEscala = graficoLinhas === resumoMensal ? 'mensal' : escala;

  const opcoes = useMemo(() => {
    if (!graficoLinhas.length) return null;
    return {
      extrato: opcaoExtrato(graficoLinhas, graficoEscala),
      agua: opcaoPEtpEtr(graficoLinhas, graficoEscala),
      arm: opcaoArmazenamento(graficoLinhas, graficoEscala, d.parametros.cad_mm),
    };
  }, [graficoLinhas, graficoEscala, d?.parametros?.cad_mm]);

  const meses = (() => {
    const [a1, m1] = inicio.split('-').map(Number);
    const [a2, m2] = fim.split('-').map(Number);
    return (a2 - a1) * 12 + (m2 - m1) + 1;
  })();

  return (
    <div className="pagina">
      <CabecalhoPagina titulo="Balanço hídrico">
        Balanço climatológico de Thornthwaite & Mather (1955), com a evapotranspiração potencial de Thornthwaite (1948),
        calculado com a chuva e a temperatura do posto escolhido.
      </CabecalhoPagina>

      <div className="filtros" role="search" aria-label="Parâmetros do balanço">
        <div className="filtros__linha">
          <Campo rotulo="Posto">
            {(id) => (
              <select id={id} className="entrada entrada--larga" value={codigo} onChange={(e) => mudar({ posto: e.target.value })}>
                {lista.map((x) => (
                  <option key={x.codigo} value={x.codigo}>
                    {x.fonte === 'esalq' ? 'ESALQ/USP (Piracicaba)' : `${x.nome} – ${x.codigo}`}
                    {x.fonte !== 'esalq' && !x.tem_dados ? ' (só NASA POWER por enquanto)' : ''}
                  </option>
                ))}
                <option value="COORD">Outro local (coordenadas)</option>
              </select>
            )}
          </Campo>
          {coordenadas ? (
            <>
              <CampoNumero rotulo="Latitude" unidade="°" valor={lat} aoMudar={(v) => mudar({ lat: v })} min={-34} max={6} />
              <CampoNumero rotulo="Longitude" unidade="°" valor={lon} aoMudar={(v) => mudar({ lon: v })} min={-75} max={-30} />
            </>
          ) : (
            <Campo rotulo="Dados" grupo>
              {() => (
                <Segmentado
                  rotulo="Origem dos dados"
                  opcoes={[
                    { id: 'posto', rotulo: 'Medidos no posto' },
                    { id: 'nasa', rotulo: 'NASA POWER' },
                  ]}
                  valor={usarNasa ? 'nasa' : 'posto'}
                  aoMudar={(v) => mudar({ dados: v === 'nasa' ? 'nasa' : null })}
                />
              )}
            </Campo>
          )}
          <CampoNumero
            rotulo="CAD"
            unidade="mm"
            valor={cad}
            aoMudar={(v) => mudar({ cad: v })}
            min={1}
            max={1000}
            dica="Água disponível no solo"
          />
        </div>
        <div className="filtros__linha">
          <Campo rotulo="Período" grupo>
            {() => (
              <Segmentado
                rotulo="Período do balanço"
                opcoes={PRESETS}
                valor={preset}
                aoMudar={(v) =>
                  mudar(v === 'outro' ? { periodo: v, inicio, fim, escala: null } : { periodo: v, inicio: null, fim: null, escala: null })
                }
              />
            )}
          </Campo>
          {preset === 'outro' && (
            <div className="filtros__datas">
              <label className="filtros__data">
                <span className="campo__rotulo">De</span>
                <input type="month" className="entrada" value={inicio} onChange={(e) => e.target.value && mudar({ inicio: e.target.value })} />
              </label>
              <label className="filtros__data">
                <span className="campo__rotulo">até</span>
                <input type="month" className="entrada" value={fim} onChange={(e) => e.target.value && mudar({ fim: e.target.value })} />
              </label>
            </div>
          )}
          <Campo rotulo="Passo" grupo>
            {() => (
              <Segmentado
                rotulo="Passo do balanço"
                opcoes={[
                  { id: 'mensal', rotulo: 'Mensal' },
                  { id: 'diario', rotulo: 'Diário' },
                ]}
                valor={escala}
                aoMudar={(v) => mudar({ escala: v })}
              />
            )}
          </Campo>
        </div>
        <p className="situacao">
          <span>
            {mesAno(`${inicio}-01`)} a {mesAno(`${fim}-01`)} ({meses} {meses === 1 ? 'mês' : 'meses'})
            {usarNasa
              ? '. Fonte: NASA POWER, estimativa por satélite e reanálise (grade de cerca de 50 km), não medida no posto.'
              : posto?.fim_dados
                ? `. Dados do posto até ${posto.fim_dados.split('-').reverse().join('/')}.`
                : '.'}
          </span>
        </p>
      </div>

      {postos.erro && <Aviso tipo="erro">{postos.erro.message}</Aviso>}
      {bh.erro && (
        <Aviso
          tipo="erro"
          titulo="Não foi possível calcular o balanço"
          acao={
            !usarNasa && (
              <button type="button" className="botao" onClick={() => mudar({ dados: 'nasa' })}>
                Calcular com NASA POWER
              </button>
            )
          }
        >
          {bh.erro.message}
        </Aviso>
      )}
      {bh.carregando && !d && <Carregando texto={usarNasa ? 'Buscando dados no NASA POWER…' : 'Calculando…'} />}

      {d && !bh.erro && (
        <div className={bh.carregando ? 'esmaecido' : undefined}>
          {d.avisos.length > 0 && (
            <Aviso tipo="atencao" titulo="Atenção aos dados">
              <ul className="lista-avisos">
                {d.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </Aviso>
          )}

          <section className="secao" aria-labelledby="titulo-resultado">
            <h2 id="titulo-resultado" className="secao__titulo">
              {d.posto.nome}: {mesAno(d.parametros.inicio)} a {mesAno(d.parametros.fim)}
            </h2>
            <Ficha
              titulo="Totais do período"
              itens={[
                { rotulo: 'Chuva (P)', valor: num(d.totais.p_mm, 0), unidade: 'mm' },
                { rotulo: 'Evapotranspiração potencial (ETP)', valor: num(d.totais.etp_mm, 0), unidade: 'mm' },
                { rotulo: 'Evapotranspiração real (ETR)', valor: num(d.totais.etr_mm, 0), unidade: 'mm' },
                { rotulo: 'Deficiência hídrica (DEF)', valor: num(d.totais.def_mm, 0), unidade: 'mm' },
                { rotulo: 'Excedente hídrico (EXC)', valor: num(d.totais.exc_mm, 0), unidade: 'mm' },
                {
                  rotulo: 'Variação do armazenamento',
                  valor: num(d.totais.alt_mm, 0),
                  unidade: 'mm',
                  nota: `CAD de ${num(d.parametros.cad_mm, 0)} mm; começou com ${num(d.parametros.arm_inicial_mm, 0)} mm`,
                },
              ]}
            />
          </section>

          {opcoes && (
            <div className="multiplos multiplos--bh">
              <BlocoGrafico
                titulo="Extrato do balanço hídrico"
                nota={`Excedente acima de zero, deficiência abaixo (mm por ${graficoEscala === 'diario' ? 'dia' : 'mês'})`}
              >
                <Grafico opcao={opcoes.extrato} altura={260} descricao="Extrato do balanço hídrico: excedente e deficiência" />
              </BlocoGrafico>
              <BlocoGrafico titulo="Chuva, ETP e ETR" nota="Chuva em barras; evapotranspiração potencial e real em linhas (mm)">
                <Grafico opcao={opcoes.agua} altura={260} descricao="Chuva, evapotranspiração potencial e real" />
              </BlocoGrafico>
              <BlocoGrafico titulo="Água armazenada no solo" nota="ARM ao fim de cada passo, com a capacidade de água disponível (CAD)">
                <Grafico opcao={opcoes.arm} altura={240} descricao="Armazenamento de água no solo" />
              </BlocoGrafico>
            </div>
          )}

          <section className="secao" aria-labelledby="titulo-tabela-bh">
            <h2 id="titulo-tabela-bh" className="secao__titulo">
              Balanço sequencial {escala === 'diario' ? 'diário' : 'mensal'} (mm)
            </h2>
            <TabelaLonga linhas={seq} legenda="Balanço hídrico sequencial" />
            {escala === 'diario' && resumoMensal.length > 0 && (
              <>
                <h3 className="secao__subtitulo">Resumo mensal do balanço diário</h3>
                <Tabela
                  legenda="Resumo mensal"
                  colunas={COLUNAS_BH.filter((c) => !['neg_ac_mm', 'alt_mm'].includes(c.chave))}
                  linhas={resumoMensal}
                  compacta
                />
              </>
            )}
            <Downloads
              caminho="/api/balanco/download"
              params={consulta}
              variavelR="bh"
            />
          </section>

          <section className="secao" aria-labelledby="titulo-normal">
            <h2 id="titulo-normal" className="secao__titulo">Balanço normal do período</h2>
            <p className="secao__texto">
              Médias de cada mês entre {d.base_normais.inicio.split('-').reverse().join('/')} e{' '}
              {d.base_normais.fim.split('-').reverse().join('/')}. Pela classificação de Thornthwaite (1948), o índice hídrico
              é Im = {num(d.indices.indice_hidrico_im, 1)} (umidade Ih = {num(d.indices.indice_umidade_ih, 1)}, aridez
              Ia = {num(d.indices.indice_aridez_ia, 1)}): clima <strong>{d.indices.tipo_climatico}</strong>, {d.indices.descricao.toLowerCase()}.
              Índice de calor I = {num(d.indice_calor.I, 2)}; a = {num(d.indice_calor.a, 3)}.
            </p>
            <Tabela
              legenda="Balanço hídrico normal"
              colunas={[{ chave: 'nome', rotulo: 'Mês', tipo: 'texto' }, ...COLUNAS_BH.slice(1)]}
              linhas={d.normal.map((l) => ({ ...l, id: l.mes, nome: NOMES_MES[l.mes - 1] }))}
              rodape={{ nome: 'Ano', ...d.totais_normal }}
            />
          </section>
        </div>
      )}
    </div>
  );
}

function TabelaLonga({ linhas, legenda }) {
  const [limite, setLimite] = useState(120);
  const temEstimadas = linhas.some((l) => l.p_estimada || l.t_estimada);
  const colunas = temEstimadas
    ? [...COLUNAS_BH, { chave: 'estimado', rotulo: 'Estimado', tipo: 'texto' }]
    : linhas.some((l) => l.cobertura_p_pct !== undefined)
      ? [...COLUNAS_BH, { chave: 'cobertura_p_pct', rotulo: 'Dados de P (%)', tipo: 'num', casas: 0 }]
      : COLUNAS_BH;
  const visiveis = linhas.slice(0, limite).map((l, i) => ({
    ...l,
    id: i,
    estimado: [l.p_estimada && 'P', l.t_estimada && 'T'].filter(Boolean).join(', '),
  }));
  return (
    <>
      <Tabela legenda={legenda} colunas={colunas} linhas={visiveis} compacta />
      {linhas.length > limite && (
        <button type="button" className="botao" onClick={() => setLimite((x) => x + 240)}>
          Mostrar mais {Math.min(240, linhas.length - limite)} de {linhas.length - limite} linhas restantes
        </button>
      )}
    </>
  );
}

