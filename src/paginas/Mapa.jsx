import { useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useApi } from '../api.js';
import { linhasDaSerie } from '../colunas.js';
import Grafico from '../componentes/Grafico.jsx';
import MapaSP from '../componentes/MapaSP.jsx';
import { Aviso, Campo, Carregando, Segmentado, TabelaDobravel } from '../componentes/Comuns.jsx';
import { dataBR, dataHoraBR, isoData, MESES, MESES_CURTOS, num, paraData, periodoExtenso } from '../formato.js';
import { POR_PASSO, opcaoPluviograma } from '../graficos/opcoes.js';
import { ultimoPosto } from '../meta.jsx';
import { descricaoPosto, nomeCurto, nomePosto, usePostos } from '../postos.js';

// Rampa ordinal azul (validada: começa clara mas ainda com contraste ≥ 2:1 sobre o mapa, #fbfcfb)
const RAMPA = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281'];
const COBERTURA_MINIMA = 80;

const MODOS = [
  { id: 'mes', rotulo: 'Mês' },
  { id: 'ano', rotulo: 'Ano' },
  { id: '12m', rotulo: '12 meses' },
  { id: 'outro', rotulo: 'Outro período' },
];

const doisDig = (n) => String(n).padStart(2, '0');
const ultimoDiaDoMes = (a, m) => new Date(a, m, 0).getDate(); // m = 1..12

/** Mês completo mais recente até a data (se a data não é o fim do mês, o mês anterior). */
function mesCompleto(iso) {
  const d = paraData(iso) ?? new Date();
  let a = d.getFullYear();
  let m = d.getMonth() + 1;
  if (d.getDate() < ultimoDiaDoMes(a, m)) {
    m -= 1;
    if (m === 0) {
      m = 12;
      a -= 1;
    }
  }
  return { a, m };
}

function periodoDoMapa(params, ref) {
  const modo = params.get('periodo') ?? 'mes';
  const { a: aRef, m: mRef } = mesCompleto(ref.inmet ?? ref.esalq);
  const fimRef = `${aRef}-${doisDig(mRef)}-${ultimoDiaDoMes(aRef, mRef)}`;
  if (modo === 'ano') {
    const ano = Number(params.get('ano') ?? aRef - (mRef === 12 ? 0 : 1));
    const fim = ano === aRef ? fimRef : `${ano}-12-31`;
    return { modo, ano, inicio: `${ano}-01-01`, fim, texto: ano === aRef && mRef < 12 ? `${ano} (janeiro a ${MESES[mRef - 1]})` : String(ano) };
  }
  if (modo === '12m') {
    const ini = new Date(aRef, mRef - 12, 1);
    return {
      modo,
      inicio: isoData(ini),
      fim: fimRef,
      texto: `${MESES_CURTOS[ini.getMonth()]}/${ini.getFullYear()} a ${MESES_CURTOS[mRef - 1]}/${aRef}`,
    };
  }
  if (modo === 'outro') {
    const valida = (t) => (t && /^\d{4}-\d{2}-\d{2}$/.test(t) && !Number.isNaN(paraData(t).getTime()) ? t : null);
    const fim = valida(params.get('fim')) ?? fimRef;
    const inicio = valida(params.get('inicio')) ?? isoData(new Date(paraData(fim).getTime() - 29 * 86400000));
    return { modo, inicio, fim, texto: periodoExtenso(inicio, fim) };
  }
  const [a, m] = (params.get('mes') ?? `${aRef}-${doisDig(mRef)}`).split('-').map(Number);
  return {
    modo: 'mes',
    mes: `${a}-${doisDig(m)}`,
    inicio: `${a}-${doisDig(m)}-01`,
    fim: `${a}-${doisDig(m)}-${ultimoDiaDoMes(a, m)}`,
    texto: `${MESES[m - 1]} de ${a}`,
  };
}

/** Limites das classes: quantis arredondados a 2 algarismos significativos. */
function quebras(valores) {
  const v = valores.filter((x) => x !== null && Number.isFinite(x)).sort((a, b) => a - b);
  if (v.length < 4) return [];
  const redondo = (x) => {
    if (x <= 0) return 0;
    const ordem = 10 ** (Math.floor(Math.log10(x)) - 1);
    return Math.round(x / ordem) * ordem;
  };
  const q = [0.2, 0.4, 0.6, 0.8].map((p) => redondo(v[Math.min(v.length - 1, Math.floor(p * v.length))]));
  return q.filter((x, i) => x > (i ? q[i - 1] : -Infinity) && x > v[0]);
}

const classe = (valor, lim) => lim.filter((l) => valor >= l).length;

export default function Mapa() {
  const [params, setParams] = useSearchParams();
  const { dados: lista, erro: erroLista } = usePostos();
  const ref = { inmet: lista?.referencia?.ultimo_dia_inmet, esalq: lista?.referencia?.ultimo_dia_esalq };
  const periodo = lista ? periodoDoMapa(params, ref) : null;
  const selecionado = params.get('posto') ?? ultimoPosto();
  const [busca, setBusca] = useState('');
  const [ordem, setOrdem] = useState('chuva');
  const painel = useRef(null);

  const mudar = (mudancas) =>
    setParams(
      (atual) => {
        const novo = new URLSearchParams(atual);
        for (const [k, v] of Object.entries(mudancas)) {
          if (v === null || v === undefined) novo.delete(k);
          else novo.set(k, String(v));
        }
        return novo;
      },
      { replace: true },
    );

  const mapa = useApi('/api/mapa', periodo && { inicio: periodo.inicio, fim: periodo.fim }, Boolean(periodo));
  const postos = mapa.dados?.postos;

  const limites = useMemo(
    () => quebras((postos ?? []).filter((p) => p.cobertura_pct >= COBERTURA_MINIMA).map((p) => p.chuva_mm)),
    [postos],
  );

  const marcadores = useMemo(
    () =>
      (postos ?? []).map((p) => {
        const vazio = !p.dias_com_dados;
        return {
          id: p.id,
          lat: p.lat,
          lon: p.lon,
          esalq: p.fonte === 'esalq',
          vazio,
          incompleto: !vazio && p.cobertura_pct < COBERTURA_MINIMA,
          cor: vazio ? null : RAMPA[classe(p.chuva_mm, limites)],
          rotulo: nomeCurto(p),
          rotuloAcessivel: `${nomePosto(p)}: ${vazio ? 'sem dados no período' : `${num(p.chuva_mm, 1)} mm`}`,
          dados: p,
        };
      }),
    [postos, limites],
  );

  const escolher = (id) => {
    mudar({ posto: id });
    // No celular o painel fica abaixo do mapa: rola até ele
    if (window.matchMedia?.('(max-width: 900px)').matches) {
      setTimeout(() => painel.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
    }
  };

  const linhasTabela = useMemo(() => {
    let l = [...(postos ?? [])];
    if (busca.trim()) {
      const b = busca.trim().toLowerCase();
      l = l.filter((p) => `${p.nome} ${p.codigo} ${p.municipio ?? ''}`.toLowerCase().includes(b));
    }
    if (ordem === 'nome') l.sort((a, b) => nomePosto(a).localeCompare(nomePosto(b), 'pt-BR'));
    else l.sort((a, b) => (b.chuva_mm ?? -1) - (a.chuva_mm ?? -1));
    return l;
  }, [postos, busca, ordem]);

  const maxChuva = Math.max(1, ...(postos ?? []).map((p) => p.chuva_mm ?? 0));
  const atual = postos?.find((p) => p.id === selecionado) ?? lista?.postos?.find((p) => p.id === selecionado);
  const comDados = (postos ?? []).filter((p) => p.dias_com_dados > 0).length;

  return (
    <div className="pagina pagina--mapa">
      <header className="mapa-topo">
        <h1 className="mapa-topo__titulo">
          Chuva em {periodo ? periodo.texto : '…'}
        </h1>
        <p className="mapa-topo__lead">
          Escolha um posto no mapa ou na lista para ver a chuva diária, acumulada e horária, os eventos de chuva e o
          balanço hídrico.
        </p>
      </header>

      <div className="filtros" role="search" aria-label="Período do mapa">
        <div className="filtros__linha">
          <Segmentado
            rotulo="Período"
            opcoes={MODOS}
            valor={periodo?.modo}
            aoMudar={(modo) => mudar({ periodo: modo === 'mes' ? null : modo })}
          />
          {periodo?.modo === 'mes' && (
            <Campo rotulo="Mês">
              {(id) => (
                <select id={id} className="entrada" value={periodo.mes} onChange={(e) => mudar({ mes: e.target.value })}>
                  {opcoesMeses(ref).map((g) => (
                    <optgroup key={g.ano} label={String(g.ano)}>
                      {g.meses.map((m) => (
                        <option key={m.valor} value={m.valor}>
                          {m.rotulo}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              )}
            </Campo>
          )}
          {periodo?.modo === 'ano' && (
            <Campo rotulo="Ano">
              {(id) => (
                <select id={id} className="entrada" value={periodo.ano} onChange={(e) => mudar({ ano: e.target.value })}>
                  {opcoesAnos(ref).map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              )}
            </Campo>
          )}
          {periodo?.modo === 'outro' && (
            <div className="filtros__datas">
              <label className="filtros__data">
                <span className="visualmente-oculto">Data inicial</span>
                <input
                  type="date"
                  className="entrada"
                  value={periodo.inicio}
                  min="2000-01-01"
                  onChange={(e) => e.target.value && mudar({ inicio: e.target.value, fim: periodo.fim })}
                />
              </label>
              <span aria-hidden="true">a</span>
              <label className="filtros__data">
                <span className="visualmente-oculto">Data final</span>
                <input
                  type="date"
                  className="entrada"
                  value={periodo.fim}
                  onChange={(e) => e.target.value && mudar({ inicio: periodo.inicio, fim: e.target.value })}
                />
              </label>
            </div>
          )}
        </div>
        {lista && (
          <p className="situacao">
            <span>
              O INMET publica os dados uma vez por mês: as estações dele vão até{' '}
              <strong>{dataBR(ref.inmet)}</strong>. A ESALQ vai até <strong>{dataBR(ref.esalq)}</strong>.
            </span>
          </p>
        )}
      </div>

      {(erroLista || mapa.erro) && (
        <Aviso tipo="erro" titulo="Não foi possível carregar o mapa">
          {(erroLista || mapa.erro).message}
        </Aviso>
      )}
      {!postos && !mapa.erro && !erroLista && <Carregando texto="Carregando os postos…" />}

      {postos && (
        <div className={`mapa-layout${mapa.carregando ? ' esmaecido' : ''}`}>
          <figure className="mapa-figura">
            <MapaSP
              postos={marcadores}
              selecionados={[selecionado]}
              aoSelecionar={escolher}
              rotuloAcessivel={`Mapa de São Paulo com ${postos.length} postos; chuva em ${periodo.texto}`}
              dica={(m) => <DicaPosto p={m.dados} />}
            />
            <figcaption>
              <Legenda limites={limites} />
              <p className="mapa-figura__nota">
                {comDados} de {postos.length} postos com dados no período. Cada cor reúne cerca de um quinto dos postos
                com dados completos.
              </p>
            </figcaption>
          </figure>

          <aside className="lado" ref={painel} aria-live="polite" aria-label="Posto selecionado">
            {atual ? (
              <PainelDoPosto p={atual} periodo={periodo} key={`${atual.id}-${periodo.inicio}-${periodo.fim}`} />
            ) : (
              <p className="lado__vazio">Escolha um posto no mapa.</p>
            )}
          </aside>
        </div>
      )}

      {postos && (
        <section className="secao" aria-labelledby="titulo-lista">
          <div className="secao__topo">
            <h2 id="titulo-lista" className="secao__titulo">
              Todos os postos
            </h2>
            <div className="lista-controles">
              <label className="campo">
                <span className="visualmente-oculto">Buscar posto</span>
                <input
                  className="entrada"
                  type="search"
                  placeholder="Buscar nome, município ou código"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                />
              </label>
              <Segmentado
                rotulo="Ordenar por"
                opcoes={[
                  { id: 'chuva', rotulo: 'Mais chuva' },
                  { id: 'nome', rotulo: 'Nome' },
                ]}
                valor={ordem}
                aoMudar={setOrdem}
              />
            </div>
          </div>
          <div className="tabela-envolve" tabIndex={0} aria-label="Postos e chuva no período">
            <table className="tabela tabela--postos">
              <caption className="visualmente-oculto">Chuva de cada posto em {periodo.texto}</caption>
              <thead>
                <tr>
                  <th scope="col">Posto</th>
                  <th scope="col" className="num">
                    Chuva (mm)
                  </th>
                  <th scope="col" className="coluna-barra" aria-hidden="true" />
                  <th scope="col" className="num">
                    Dias com dados
                  </th>
                  <th scope="col" className="num">
                    Maior chuva em 1 dia
                  </th>
                  <th scope="col">Dados até</th>
                </tr>
              </thead>
              <tbody>
                {linhasTabela.map((p) => (
                  <tr key={p.id} className={p.id === selecionado ? 'destaque' : undefined}>
                    <td>
                      <button type="button" className="link-botao" onClick={() => escolher(p.id)}>
                        {nomePosto(p)}
                      </button>
                      <span className="posto-nome__rede">
                        {p.fonte === 'esalq' ? 'ESALQ/USP, 15 min' : `INMET ${p.codigo}, ${p.tem_registros ? 'horária' : 'diária no site'}`}
                      </span>
                    </td>
                    <td className="num">{num(p.chuva_mm, 1)}</td>
                    <td className="coluna-barra" aria-hidden="true">
                      {p.chuva_mm !== null && (
                        <span
                          className={`barra-chuva${p.cobertura_pct < COBERTURA_MINIMA ? ' barra-chuva--incompleta' : ''}`}
                          style={{ width: `${(p.chuva_mm / maxChuva) * 100}%` }}
                        />
                      )}
                    </td>
                    <td className="num">
                      {p.dias_com_dados} de {mapa.dados.periodo.dias}
                    </td>
                    <td className="num">
                      {p.chuva_max_dia_mm !== null ? `${num(p.chuva_max_dia_mm, 1)} (${dataBR(p.data_chuva_max_dia).slice(0, 5)})` : '–'}
                    </td>
                    <td>{dataBR(p.fim_dados)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function opcoesMeses(ref) {
  const fim = paraData(ref.esalq ?? ref.inmet) ?? new Date();
  const { a: aInmet, m: mInmet } = mesCompleto(ref.inmet ?? ref.esalq);
  const grupos = [];
  for (let a = fim.getFullYear(); a >= 2001; a -= 1) {
    const meses = [];
    const ultimo = a === fim.getFullYear() ? fim.getMonth() + 1 : 12;
    for (let m = ultimo; m >= 1; m -= 1) {
      const soEsalq = a > aInmet || (a === aInmet && m > mInmet);
      meses.push({ valor: `${a}-${doisDig(m)}`, rotulo: `${MESES[m - 1]}${soEsalq ? ' (só ESALQ até agora)' : ''}` });
    }
    grupos.push({ ano: a, meses });
  }
  return grupos;
}

function opcoesAnos(ref) {
  const { a } = mesCompleto(ref.inmet ?? ref.esalq);
  const anos = [];
  for (let x = a; x >= 2001; x -= 1) anos.push(x);
  return anos;
}

function Legenda({ limites }) {
  const faixas = limites.length
    ? [`até ${num(limites[0], 0)}`, ...limites.slice(0, -1).map((l, i) => `${num(l, 0)}–${num(limites[i + 1], 0)}`), `${num(limites.at(-1), 0)} ou mais`]
    : ['chuva no período'];
  return (
    <div className="legenda-mapa">
      <span className="legenda-mapa__titulo">Chuva no período (mm)</span>
      <ul className="legenda-mapa__faixas">
        {faixas.map((f, i) => (
          <li key={f}>
            <span className="legenda-mapa__cor" style={{ background: RAMPA[limites.length ? i : 2] }} />
            {f}
          </li>
        ))}
      </ul>
      <ul className="legenda-mapa__formas">
        <li>
          <svg width="14" height="14" aria-hidden="true">
            <circle cx="7" cy="7" r="5" fill="var(--folha)" stroke="#2a78d6" strokeWidth="2.5" />
          </svg>
          Dados em menos de {COBERTURA_MINIMA}% dos dias
        </li>
        <li>
          <svg width="14" height="14" aria-hidden="true">
            <circle cx="7" cy="7" r="4" fill="var(--folha)" stroke="var(--borda-campo)" strokeWidth="1.5" />
          </svg>
          Sem dados no período
        </li>
        <li>
          <svg width="14" height="14" aria-hidden="true">
            <rect x="3" y="3" width="8" height="8" rx="1" transform="rotate(45 7 7)" fill="#2a78d6" />
          </svg>
          ESALQ/USP
        </li>
      </ul>
    </div>
  );
}

function DicaPosto({ p }) {
  return (
    <>
      <strong className="dica-posto__nome">{nomePosto(p)}</strong>
      {p.dias_com_dados ? (
        <>
          <span className="dica-posto__valor">{num(p.chuva_mm, 1)} mm</span>
          <span className="dica-posto__nota">
            dados em {p.dias_com_dados} {p.dias_com_dados === 1 ? 'dia' : 'dias'}
            {p.cobertura_pct < 100 ? ` (${num(p.cobertura_pct, 0)}% do período)` : ''}
          </span>
        </>
      ) : (
        <span className="dica-posto__nota">sem dados no período</span>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Painel lateral: o posto escolhido no período do mapa                */
/* ------------------------------------------------------------------ */

function PainelDoPosto({ p, periodo }) {
  const dias = (Date.parse(periodo.fim) - Date.parse(periodo.inicio)) / 86400000 + 1;
  const podeHora = dias <= 45 && p.tem_registros;
  const [escala, setEscala] = useState('1D');
  const passo = podeHora ? escala : 'auto';
  const { dados, erro, carregando } = useApi(`/api/posto/${p.id}/painel`, {
    inicio: periodo.inicio,
    fim: periodo.fim,
    passo,
  });
  const r = dados?.resumo;
  const serie = dados?.serie;
  const opcao = useMemo(() => (serie?.t?.length ? opcaoPluviograma(serie, dados.passo) : null), [serie, dados?.passo]);
  const busca = `?inicio=${periodo.inicio}&fim=${periodo.fim}`;
  const horario = p.resolucao_min === 60;

  return (
    <div className="lado__conteudo">
      <p className="lado__rede">{descricaoPosto(p)}</p>
      <h2 className="lado__nome">{nomePosto(p)}</h2>
      {p.fonte !== 'esalq' && p.municipio && <p className="lado__local">{p.municipio}/SP, {num(p.alt, 0)} m de altitude</p>}

      {erro && <Aviso tipo="erro">{erro.message}</Aviso>}
      {!dados && !erro && <Carregando />}

      {r && (
        <div className={carregando ? 'esmaecido' : undefined}>
          {r.chuva_total_mm === null ? (
            p.tem_dados ? (
              <Aviso tipo="info" titulo="Sem dados neste período">
                Os dados deste posto vão de {dataBR(p.inicio_dados)} a {dataBR(p.fim_dados)}.
              </Aviso>
            ) : (
              <Aviso tipo="atencao" titulo="Ainda não há dados deste posto no site">
                Os dados do INMET entram pela atualização automática. Rodando no seu computador, traga os dados com{' '}
                <code>git pull</code>.
              </Aviso>
            )
          ) : (
            <>
              <p className="lado__total">
                <span className="lado__numero">{num(r.chuva_total_mm, 1)}</span>
                <span className="lado__unidade">mm acumulados</span>
              </p>
              {podeHora && (
                <Segmentado
                  rotulo="Chuva por"
                  opcoes={[
                    { id: '1D', rotulo: 'Por dia' },
                    { id: '1h', rotulo: 'Por hora' },
                  ]}
                  valor={escala}
                  aoMudar={setEscala}
                />
              )}
              {opcao && (
                <>
                  <Grafico
                    opcao={opcao}
                    altura={300}
                    descricao={`Chuva ${POR_PASSO[dados.passo]} e acumulada em ${periodo.texto}: ${num(r.chuva_total_mm, 1)} mm`}
                  />
                  <TabelaDobravel
                    legenda="Chuva por intervalo e acumulada"
                    colunas={[
                      { chave: 't', rotulo: 'Até', tipo: ['15min', '1h'].includes(dados.passo) ? 'datahora' : 'data' },
                      { chave: 'chuva_mm', rotulo: `Chuva ${POR_PASSO[dados.passo]} (mm)`, tipo: 'num', casas: 1 },
                      { chave: 'chuva_acum_mm', rotulo: 'Acumulada (mm)', tipo: 'num', casas: 1 },
                    ]}
                    linhas={linhasDaSerie(serie, ['chuva_mm', 'chuva_acum_mm'])}
                  />
                </>
              )}
              <dl className="lado__ficha">
                <div>
                  <dt>Dias com chuva (≥ 1 mm)</dt>
                  <dd>{r.dias_chuva}</dd>
                </div>
                <div>
                  <dt>Maior chuva em um dia</dt>
                  <dd>
                    {num(r.chuva_max_diaria.valor, 1)} mm
                    {r.chuva_max_diaria.quando && <span> em {dataBR(r.chuva_max_diaria.quando)}</span>}
                  </dd>
                </div>
                {r.resolucao_min !== 1440 && r.intensidade_max.valor !== null && (
                  <div>
                    <dt>Maior intensidade ({horario ? '1 h' : '15 min'})</dt>
                    <dd>
                      {num(r.intensidade_max.valor, 1)} mm/h
                      {r.intensidade_max.valor > 0 && <span> em {dataHoraBR(r.intensidade_max.quando)}</span>}
                    </dd>
                  </div>
                )}
                {r.temp_media_c !== null && (
                  <div>
                    <dt>Temperatura média</dt>
                    <dd>{num(r.temp_media_c, 1)} °C</dd>
                  </div>
                )}
                <div>
                  <dt>Dados válidos</dt>
                  <dd>{num(r.cobertura_pct, 0)}% do período</dd>
                </div>
              </dl>
              {!p.tem_registros && (
                <p className="texto-pequeno">
                  Por enquanto só há totais diários deste posto no site; os horários entram na próxima atualização.
                </p>
              )}
            </>
          )}
        </div>
      )}

      <div className="lado__acoes">
        <Link className="botao botao--primario" to={`/posto/${p.id}${busca}`}>
          Abrir o painel do posto
        </Link>
        <Link className="botao" to={`/balanco?posto=${p.codigo}`}>
          Balanço hídrico
        </Link>
        <Link className="botao" to={`/comparar?postos=${p.id}`}>
          Comparar com outros
        </Link>
      </div>
    </div>
  );
}
