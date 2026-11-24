import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useApi } from '../api.js';
import Grafico from '../componentes/Grafico.jsx';
import MapaSP from '../componentes/MapaSP.jsx';
import {
  Aviso, BlocoGrafico, CabecalhoPagina, Campo, CampoNumero, Carregando, Segmentado, Tabela, TabelaDobravel,
} from '../componentes/Comuns.jsx';
import { mesAno, num } from '../formato.js';
import { opcaoBarrasChuva, opcaoDefExcPostos, opcaoExtrato, opcaoParPostos } from '../graficos/opcoes.js';
import { distanciaKm, nomeCurto, nomePosto, ordenarParaLista, usePostos } from '../postos.js';

const PRESETS = [
  { id: '1a', rotulo: '1 ano', meses: 12 },
  { id: '5a', rotulo: '5 anos', meses: 60 },
  { id: '10a', rotulo: '10 anos', meses: 120 },
  { id: '20a', rotulo: '20 anos', meses: 240 },
  { id: 'outro', rotulo: 'Personalizado' },
];

const VARIAVEIS = [
  { id: 'chuva_diaria', rotulo: 'Chuva diária' },
  { id: 'chuva_mensal', rotulo: 'Chuva mensal' },
  { id: 'temp_mensal', rotulo: 'Temperatura mensal' },
];

const NOTA_VARIAVEL = {
  chuva_diaria:
    'Mostra se chove nos mesmos dias nos dois postos. Cai com a distância e é a melhor medida de quanto um posto representa o outro.',
  chuva_mensal:
    'Alta mesmo entre postos distantes, porque todos seguem o mesmo ciclo de verão chuvoso e inverno seco. É a usada para preencher falhas de um posto com o outro.',
  temp_mensal: 'Quase sempre perto de 1: a temperatura varia de forma parecida em toda a região.',
};

const MAX_POSTOS = 6;

function somarMeses(aaaamm, n) {
  const [a, m] = aaaamm.split('-').map(Number);
  const d = new Date(a, m - 1 + n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** Último mês completo até a data. */
function ultimoMesCompleto(iso) {
  if (!iso) return null;
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number);
  const ultimo = new Date(a, m, 0).getDate();
  return d >= ultimo ? `${a}-${String(m).padStart(2, '0')}` : somarMeses(`${a}-${String(m).padStart(2, '0')}`, -1);
}

export default function Comparar() {
  const [params, setParams] = useSearchParams();
  const { dados: lista } = usePostos();
  const todos = lista?.postos ?? [];

  const ids = (params.get('postos') ?? '').split(',').filter(Boolean).slice(0, MAX_POSTOS);
  const preset = params.get('periodo') ?? '10a';
  const cad = Number(params.get('cad') ?? 100);
  const variavel = params.get('corr') ?? 'chuva_diaria';

  const fimRef = ultimoMesCompleto(lista?.referencia?.ultimo_dia_inmet ?? lista?.referencia?.ultimo_dia_esalq);
  const p = PRESETS.find((x) => x.id === preset) ?? PRESETS[2];
  const inicio = fimRef && (preset === 'outro' ? params.get('inicio') ?? somarMeses(fimRef, -119) : somarMeses(fimRef, -(p.meses - 1)));
  const fim = fimRef && (preset === 'outro' ? params.get('fim') ?? fimRef : fimRef);

  const mudar = (mudancas) =>
    setParams((atual) => {
      const novo = new URLSearchParams(atual);
      for (const [k, v] of Object.entries(mudancas)) {
        if (v === null || v === undefined || v === '') novo.delete(k);
        else novo.set(k, String(v));
      }
      return novo;
    });
  const definirPostos = (novos) => mudar({ postos: novos.join(',') });
  const alternar = (id) => {
    if (ids.includes(id)) definirPostos(ids.filter((x) => x !== id));
    else if (ids.length < MAX_POSTOS) definirPostos([...ids, id]);
  };

  const pronto = ids.length >= 2 && inicio && fim;
  const cmp = useApi('/api/comparar', pronto ? { postos: ids.join(','), inicio, fim, cad } : null, Boolean(pronto));
  const d = cmp.dados;

  const porId = Object.fromEntries(todos.map((x) => [x.id, x]));
  const escolhidos = ids.map((id) => porId[id]).filter(Boolean);
  const referencia = escolhidos[0];
  const proximos = referencia
    ? todos
        .filter((x) => !ids.includes(x.id) && x.tem_dados)
        .map((x) => ({ ...x, km: distanciaKm(referencia, x) }))
        .sort((a, b) => a.km - b.km)
        .slice(0, 4)
    : [];

  const marcadores = todos.map((x) => ({
    id: x.id,
    lat: x.lat,
    lon: x.lon,
    esalq: x.fonte === 'esalq',
    vazio: !ids.includes(x.id),
    cor: '#2a78d6',
    rotulo: nomeCurto(x),
    rotuloAcessivel: `${nomePosto(x)}${ids.includes(x.id) ? ' (na comparação)' : ''}`,
  }));

  return (
    <div className="pagina">
      <CabecalhoPagina titulo="Comparar postos">
        Balanço hídrico de até {MAX_POSTOS} postos no mesmo período e a correlação entre eles: quanto a chuva e a
        temperatura de um acompanham as do outro.
      </CabecalhoPagina>

      <div className="comparar-escolha">
        <div className="comparar-escolha__lista">
          <h2 className="secao__subtitulo">Postos na comparação</h2>
          {escolhidos.length === 0 && <p className="texto-pequeno">Nenhum ainda. Escolha na lista ou clique no mapa.</p>}
          <ul className="fichas-postos">
            {escolhidos.map((x, i) => (
              <li key={x.id} className="ficha-posto">
                <span className="ficha-posto__nome">{nomePosto(x)}</span>
                <span className="ficha-posto__info">
                  {x.fonte === 'esalq' ? 'ESALQ/USP' : `INMET ${x.codigo}`}
                  {i > 0 && referencia ? `, a ${num(distanciaKm(referencia, x), 0)} km de ${nomeCurto(referencia)}` : ''}
                </span>
                <button type="button" className="ficha-posto__tirar" onClick={() => alternar(x.id)} aria-label={`Tirar ${nomePosto(x)} da comparação`}>
                  Tirar
                </button>
              </li>
            ))}
          </ul>
          {ids.length < MAX_POSTOS && (
            <Campo rotulo="Adicionar posto">
              {(cid) => (
                <select id={cid} className="entrada entrada--larga" value="" onChange={(e) => e.target.value && alternar(e.target.value)}>
                  <option value="">Escolha um posto…</option>
                  {ordenarParaLista(todos)
                    .filter((x) => !ids.includes(x.id))
                    .map((x) => (
                      <option key={x.id} value={x.id} disabled={!x.tem_dados}>
                        {x.fonte === 'esalq' ? 'ESALQ/USP – Piracicaba' : `${x.nome} (${x.codigo})`}
                        {x.tem_dados ? '' : ' – sem dados ainda'}
                      </option>
                    ))}
                </select>
              )}
            </Campo>
          )}
          {proximos.length > 0 && ids.length < MAX_POSTOS && (
            <div className="proximos">
              <span className="texto-pequeno">Mais perto de {nomeCurto(referencia)}:</span>
              {proximos.map((x) => (
                <button key={x.id} type="button" className="botao botao--pequeno" onClick={() => alternar(x.id)}>
                  {nomeCurto(x)} ({num(x.km, 0)} km)
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="comparar-escolha__mapa">
          {todos.length > 0 && (
            <MapaSP
              postos={marcadores}
              selecionados={ids}
              aoSelecionar={alternar}
              rotulosFixos
              rotuloAcessivel="Mapa dos postos: clique para incluir ou tirar da comparação"
              dica={(m) => (
                <>
                  <strong className="dica-posto__nome">{m.rotulo}</strong>
                  <span className="dica-posto__nota">{ids.includes(m.id) ? 'clique para tirar' : 'clique para incluir'}</span>
                </>
              )}
            />
          )}
        </div>
      </div>

      <div className="filtros" role="search" aria-label="Período e parâmetros">
        <div className="filtros__linha">
          <Segmentado rotulo="Período" opcoes={PRESETS} valor={preset} aoMudar={(id) => mudar({ periodo: id })} />
          {preset === 'outro' && (
            <>
              <Campo rotulo="De">
                {(cid) => (
                  <input id={cid} type="month" className="entrada" value={inicio ?? ''} min="2000-01" onChange={(e) => e.target.value && mudar({ inicio: e.target.value, fim })} />
                )}
              </Campo>
              <Campo rotulo="Até">
                {(cid) => (
                  <input id={cid} type="month" className="entrada" value={fim ?? ''} onChange={(e) => e.target.value && mudar({ inicio, fim: e.target.value })} />
                )}
              </Campo>
            </>
          )}
          <CampoNumero rotulo="CAD" unidade="mm" valor={cad} aoMudar={(v) => mudar({ cad: v })} min={1} max={1000} dica="Água disponível no solo" />
        </div>
        {inicio && (
          <p className="situacao">
            <span>
              De {mesAno(`${inicio}-01`)} a {mesAno(`${fim}-01`)}. Para cada posto, os meses sem dados são completados com a
              normal do próprio posto (veja os avisos).
            </span>
          </p>
        )}
      </div>

      {ids.length < 2 && (
        <Aviso tipo="info" titulo="Escolha pelo menos dois postos">
          Comece por um posto e use as sugestões dos mais próximos, ou clique nos postos do mapa.
        </Aviso>
      )}
      {cmp.erro && (
        <Aviso tipo="erro" titulo="Não foi possível comparar">
          {cmp.erro.message}
        </Aviso>
      )}
      {pronto && !d && !cmp.erro && <Carregando texto="Calculando o balanço de cada posto…" />}

      {d && pronto && (
        <div className={cmp.carregando ? 'esmaecido' : undefined}>
          <Resultados d={d} inicio={inicio} fim={fim} variavel={variavel} mudarVariavel={(v) => mudar({ corr: v })} />
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function Resultados({ d, inicio, fim, variavel, mudarVariavel }) {
  const validos = useMemo(() => d.postos.filter((x) => !x.erro), [d]);
  const comErro = d.postos.filter((x) => x.erro);
  const ref = d.postos[0].posto;

  const linhasTabela = d.postos.map((x, i) => ({
    id: x.posto.id,
    nome: nomePosto(x.posto),
    km: i === 0 ? null : distanciaKm(ref, x.posto),
    p: x.totais?.p_mm,
    etp: x.totais?.etp_mm,
    etr: x.totais?.etr_mm,
    def: x.totais?.def_mm,
    exc: x.totais?.exc_mm,
    im: x.indices?.indice_hidrico_im,
    tipo: x.indices ? `${x.indices.tipo_climatico}, ${x.indices.descricao}` : x.erro,
    cob: x.cobertura_p_pct,
  }));

  const opcaoTotais = useMemo(
    () => opcaoDefExcPostos(validos.map((x) => ({ nome: nomeCurto(x.posto), def: x.totais.def_mm, exc: x.totais.exc_mm }))),
    [validos],
  );

  // Mesma escala vertical em todos os gráficos pequenos
  const limitesExtrato = useMemo(() => {
    const exc = Math.max(10, ...validos.flatMap((x) => x.mensal.map((l) => l.exc_mm ?? 0)));
    const def = Math.max(10, ...validos.flatMap((x) => x.mensal.map((l) => l.def_mm ?? 0)));
    return { min: -Math.ceil(def / 10) * 10, max: Math.ceil(exc / 10) * 10 };
  }, [validos]);
  const maxChuva = useMemo(
    () => Math.ceil(Math.max(10, ...validos.flatMap((x) => x.mensal.map((l) => l.p_mm ?? 0))) / 50) * 50,
    [validos],
  );

  const baixarCsv = () => {
    const cab = ['posto', 'codigo', 'mes', 'p_mm', 't_c', 'etp_mm', 'etr_mm', 'def_mm', 'exc_mm', 'arm_mm', 'cobertura_p_pct', 'cobertura_t_pct'];
    const linhas = validos.flatMap((x) =>
      x.mensal.map((l) =>
        [x.posto.id, x.posto.codigo, l.inicio.slice(0, 7), l.p_mm, l.t_c, l.etp_mm, l.etr_mm, l.def_mm, l.exc_mm, l.arm_mm, l.cobertura_p_pct, l.cobertura_t_pct]
          .map((v) => (v === null || v === undefined ? 'NA' : typeof v === 'number' ? Number(v.toFixed(2)) : v))
          .join(','),
      ),
    );
    const blob = new Blob([[cab.join(','), ...linhas].join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `comparacao_balanco_${inicio}_${fim}_R.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  return (
    <>
      <section className="secao" aria-labelledby="titulo-totais">
        <h2 id="titulo-totais" className="secao__titulo">
          Balanço hídrico no período
        </h2>
        <p className="secao__texto">
          Totais de {d.parametros.meses} meses com CAD de {num(d.parametros.cad_mm, 0)} mm ({d.parametros.metodo}). A
          classificação climática vem do balanço normal de cada posto.
        </p>
        <Tabela
          legenda="Balanço hídrico de cada posto"
          colunas={[
            { chave: 'nome', rotulo: 'Posto', tipo: 'texto' },
            { chave: 'km', rotulo: `Distância de ${nomeCurto(ref)} (km)`, tipo: 'num', casas: 0 },
            { chave: 'p', rotulo: 'Chuva P (mm)', tipo: 'num', casas: 0 },
            { chave: 'etp', rotulo: 'ETP (mm)', tipo: 'num', casas: 0 },
            { chave: 'etr', rotulo: 'ETR (mm)', tipo: 'num', casas: 0 },
            { chave: 'def', rotulo: 'DEF (mm)', tipo: 'num', casas: 0 },
            { chave: 'exc', rotulo: 'EXC (mm)', tipo: 'num', casas: 0 },
            { chave: 'im', rotulo: 'Im', tipo: 'num', casas: 1 },
            { chave: 'tipo', rotulo: 'Clima (Thornthwaite)', tipo: 'texto' },
            { chave: 'cob', rotulo: 'Meses com chuva medida (%)', tipo: 'num', casas: 0 },
          ]}
          linhas={linhasTabela}
        />
        {comErro.map((x) => (
          <Aviso key={x.posto.id} tipo="atencao" titulo={`${nomePosto(x.posto)}: não calculado`}>
            {x.erro}
          </Aviso>
        ))}
        {validos.some((x) => x.avisos.length) && (
          <details className="dobravel">
            <summary>Avisos sobre os dados de cada posto</summary>
            <ul className="lista-avisos">
              {validos
                .filter((x) => x.avisos.length)
                .map((x) => (
                  <li key={x.posto.id}>
                    <strong>{nomePosto(x.posto)}:</strong> {x.avisos.join(' ')}
                  </li>
                ))}
            </ul>
          </details>
        )}
        <div className="downloads__botoes">
          <button type="button" className="botao" onClick={baixarCsv}>
            Baixar os balanços mensais (CSV para R)
          </button>
        </div>
      </section>

      {validos.length > 0 && (
        <BlocoGrafico titulo="Excedente e deficiência no período" nota="Soma dos meses do período, em mm">
          <Grafico opcao={opcaoTotais} altura={320} descricao="Excedente e deficiência hídrica de cada posto no período" />
        </BlocoGrafico>
      )}

      <Correlacao d={d} inicio={inicio} fim={fim} variavel={variavel} mudarVariavel={mudarVariavel} />

      {validos.length > 0 && (
        <section className="secao" aria-labelledby="titulo-mes-a-mes">
          <h2 id="titulo-mes-a-mes" className="secao__titulo">
            Mês a mês
          </h2>
          <p className="secao__texto">Os gráficos de cada posto usam a mesma escala, para comparar de olho.</p>
          <h3 className="secao__subtitulo">Excedente (para cima) e deficiência (para baixo)</h3>
          <div className="multiplos multiplos--postos">
            {validos.map((x) => (
              <PequenoExtrato key={x.posto.id} x={x} limites={limitesExtrato} />
            ))}
          </div>
          <h3 className="secao__subtitulo">Chuva mensal</h3>
          <div className="multiplos multiplos--postos">
            {validos.map((x) => (
              <PequenaChuva key={x.posto.id} x={x} yMax={maxChuva} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function PequenoExtrato({ x, limites }) {
  const opcao = useMemo(() => opcaoExtrato(x.mensal, 'mensal', limites, false), [x.mensal, limites]);
  return (
    <section className="grafico grafico--pequeno">
      <h4 className="grafico__titulo">{nomePosto(x.posto)}</h4>
      <Grafico opcao={opcao} altura={180} descricao={`Excedente e deficiência mensais em ${nomePosto(x.posto)}`} />
    </section>
  );
}

function PequenaChuva({ x, yMax }) {
  const opcao = useMemo(
    () => opcaoBarrasChuva(x.mensal, (l) => mesAno(l.inicio), 'p_mm', 'mm', (l) => l.cobertura_p_pct < 90, yMax),
    [x.mensal, yMax],
  );
  return (
    <section className="grafico grafico--pequeno">
      <h4 className="grafico__titulo">{nomePosto(x.posto)}</h4>
      <Grafico opcao={opcao} altura={160} descricao={`Chuva mensal em ${nomePosto(x.posto)}`} />
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Matriz de correlação + dispersão do par escolhido                   */
/* ------------------------------------------------------------------ */

// Rampa azul do r baixo (claro) ao alto (escuro). O passo do meio (#3987e5) fica de fora:
// nem texto escuro nem branco chegam a 4,5:1 sobre ele.
const RAMPA_R = ['#cde2fb', '#9ec5f4', '#6da7ec', '#256abf', '#184f95', '#0d366b'];

function corDoR(r) {
  if (r === null || r === undefined) return null;
  const i = Math.max(0, Math.min(RAMPA_R.length - 1, Math.floor(Math.max(0, r) * RAMPA_R.length)));
  return { fundo: RAMPA_R[i], texto: i >= 3 ? '#ffffff' : 'var(--grafite)' };
}

function Correlacao({ d, inicio, fim, variavel, mudarVariavel }) {
  const m = d.correlacao[variavel];
  const nomes = Object.fromEntries(d.postos.map((x) => [x.posto.id, nomeCurto(x.posto)]));
  const [par, setPar] = useState(null);
  const parValido = par && m.ids.includes(par[0]) && m.ids.includes(par[1]) ? par : m.ids.length >= 2 ? [m.ids[0], m.ids[1]] : null;
  const unidade = variavel === 'chuva_diaria' ? 'dias' : 'meses';

  if (m.ids.length < 2) return null;
  return (
    <section className="secao" aria-labelledby="titulo-correlacao">
      <div className="secao__topo">
        <h2 id="titulo-correlacao" className="secao__titulo">
          Correlação entre os postos
        </h2>
        <Segmentado rotulo="Variável" opcoes={VARIAVEIS} valor={variavel} aoMudar={mudarVariavel} />
      </div>
      <p className="secao__texto">
        Coeficiente de correlação de Pearson (r), só com os {unidade} em que os dois postos têm dados. {NOTA_VARIAVEL[variavel]}{' '}
        Clique numa célula para ver os valores do par.
      </p>
      <div className="tabela-envolve" tabIndex={0} aria-label="Matriz de correlação">
        <table className="matriz">
          <caption className="visualmente-oculto">Correlação ({VARIAVEIS.find((v) => v.id === variavel).rotulo})</caption>
          <thead>
            <tr>
              <td />
              {m.ids.map((id) => (
                <th key={id} scope="col">
                  {nomes[id]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {m.ids.map((a, i) => (
              <tr key={a}>
                <th scope="row">{nomes[a]}</th>
                {m.ids.map((b, j) => {
                  const r = m.r[i][j];
                  const cor = corDoR(r);
                  if (i === j) {
                    return (
                      <td key={b} className="matriz__diagonal">
                        –
                      </td>
                    );
                  }
                  const marcado = parValido && ((parValido[0] === a && parValido[1] === b) || (parValido[0] === b && parValido[1] === a));
                  return (
                    <td key={b} className={marcado ? 'matriz__marcada' : undefined}>
                      <button
                        type="button"
                        className="matriz__celula"
                        style={cor ? { background: cor.fundo, color: cor.texto } : undefined}
                        onClick={() => setPar([a, b])}
                        aria-pressed={Boolean(marcado)}
                        aria-label={`${nomes[a]} e ${nomes[b]}: r = ${r === null ? 'sem dados suficientes' : num(r, 2)}, ${m.n[i][j]} ${unidade} em comum`}
                      >
                        <span className="matriz__r">{r === null ? '–' : num(r, 2)}</span>
                        <span className="matriz__n">{num(m.n[i][j], 0)} {unidade}</span>
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {parValido && (
        <ParDePostos a={parValido[0]} b={parValido[1]} inicio={inicio} fim={fim} variavel={variavel} key={`${parValido.join('-')}-${variavel}`} />
      )}
    </section>
  );
}

function ParDePostos({ a, b, inicio, fim, variavel }) {
  const { dados: par, erro, carregando } = useApi('/api/comparar/par', { a, b, inicio, fim, variavel });
  const opcao = useMemo(() => (par?.n ? opcaoParPostos(par) : null), [par]);
  if (erro) return <Aviso tipo="erro">{erro.message}</Aviso>;
  if (!par) return <Carregando />;
  const reg = par.regressao;
  return (
    <BlocoGrafico
      titulo={`${par.a.nome_curto} e ${par.b.nome_curto}`}
      nota={
        reg
          ? `${par.rotulo}: r = ${num(par.r, 2)} (R² = ${num(reg.r2, 2)}) com ${num(par.n, 0)} pares; postos a ${num(par.distancia_km, 0)} km. ` +
            `Reta: ${par.b.nome_curto} = ${num(reg.intercepto, 2)} + ${num(reg.inclinacao, 3)} × ${par.a.nome_curto}.`
          : `Menos de ${par.minimo} pares com dados nos dois postos: não dá para calcular a correlação.`
      }
      carregando={carregando}
    >
      {opcao && (
        <>
          <Grafico opcao={opcao} altura={380} descricao={`Dispersão de ${par.rotulo.toLowerCase()} entre ${par.a.nome_curto} e ${par.b.nome_curto}`} />
          <TabelaDobravel
            legenda={`Valores de ${par.a.nome_curto} e ${par.b.nome_curto}`}
            colunas={[
              { chave: 't', rotulo: variavel === 'chuva_diaria' ? 'Dia' : 'Mês', tipo: variavel === 'chuva_diaria' ? 'data' : 'texto' },
              { chave: 'x', rotulo: `${par.a.nome_curto} (${par.unidade})`, tipo: 'num', casas: 1 },
              { chave: 'y', rotulo: `${par.b.nome_curto} (${par.unidade})`, tipo: 'num', casas: 1 },
            ]}
            linhas={par.t.map((t, i) => ({ id: t, t: variavel === 'chuva_diaria' ? t : mesAno(`${t}-01`), x: par.x[i], y: par.y[i] }))}
          />
        </>
      )}
      <p className="texto-pequeno">
        A reta serve para estimar um posto pelo outro (preenchimento de falhas por regressão linear). Ela só é confiável
        quando r é alto e os postos são próximos. <Link to="/metodos#comparacao">Como é calculado</Link>.
      </p>
    </BlocoGrafico>
  );
}
