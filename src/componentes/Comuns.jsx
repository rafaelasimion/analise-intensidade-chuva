import { useEffect, useId, useState } from 'react';
import { dataBR, dataHoraBR, duracao, num } from '../formato.js';
import { useMeta } from '../meta.jsx';

/* ------------------------------------------------------------------ */
/* Avisos                                                             */
/* ------------------------------------------------------------------ */

const ICONES = {
  atencao: (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="aviso__icone">
      <path d="M10 2 1 18h18L10 2Z" fill="#fab219" />
      <path d="M10 8v4.5M10 15v.01" stroke="#22303a" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  ),
  erro: (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="aviso__icone">
      <circle cx="10" cy="10" r="8.5" fill="#d03b3b" />
      <path d="M10 5.5v5.5M10 14v.01" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  ),
  info: (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="aviso__icone">
      <circle cx="10" cy="10" r="8.5" fill="none" stroke="#4f5d66" strokeWidth="1.5" />
      <path d="M10 9v5M10 6v.01" stroke="#4f5d66" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  ),
};

export function Aviso({ tipo = 'info', titulo, children, acao }) {
  return (
    <div className={`aviso aviso--${tipo}`} role={tipo === 'erro' ? 'alert' : 'status'}>
      {ICONES[tipo]}
      <div className="aviso__texto">
        {titulo && <strong className="aviso__titulo">{titulo}</strong>}
        {children}
      </div>
      {acao}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Ficha (lista de valores do período)                                */
/* ------------------------------------------------------------------ */

export function Ficha({ itens, titulo = 'Resumo do período' }) {
  return (
    <dl className="ficha" aria-label={titulo}>
      {itens.filter(Boolean).map((item) => (
        <div className="ficha__item" key={item.rotulo}>
          <dt className="ficha__rotulo">{item.rotulo}</dt>
          <dd className="ficha__valor">
            {item.valor}
            {item.unidade && item.valor !== '–' && <span className="ficha__unidade"> {item.unidade}</span>}
          </dd>
          {item.nota && <dd className="ficha__nota">{item.nota}</dd>}
        </div>
      ))}
    </dl>
  );
}

/* ------------------------------------------------------------------ */
/* Tabelas                                                            */
/* ------------------------------------------------------------------ */

export function formatarCelula(valor, coluna) {
  if (valor === null || valor === undefined || valor === '') return '–';
  switch (coluna.tipo) {
    case 'num':
      return num(valor, coluna.casas ?? 1);
    case 'data':
      return dataBR(valor);
    case 'datahora':
      return dataHoraBR(valor);
    case 'duracao':
      return duracao(valor);
    case 'sim':
      return valor ? 'sim' : '';
    default:
      return String(valor);
  }
}

export function Tabela({ colunas, linhas, legenda, rodape, compacta = false, destacar }) {
  return (
    <div className={`tabela-envolve${compacta ? ' tabela-envolve--compacta' : ''}`} tabIndex={0} aria-label={legenda}>
      <table className="tabela">
        {legenda && <caption className="visualmente-oculto">{legenda}</caption>}
        <thead>
          <tr>
            {colunas.map((c) => (
              <th key={c.chave} scope="col" className={c.tipo === 'num' || c.tipo === 'duracao' ? 'num' : undefined}>
                {c.rotulo}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((l, i) => (
            <tr key={l.id ?? i} className={destacar?.(l) ? 'destaque' : undefined}>
              {colunas.map((c) => (
                <td key={c.chave} className={c.tipo === 'num' || c.tipo === 'duracao' ? 'num' : undefined}>
                  {c.render ? c.render(l) : formatarCelula(l[c.chave], c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {rodape && (
          <tfoot>
            <tr>
              {colunas.map((c) => (
                <td key={c.chave} className={c.tipo === 'num' ? 'num' : undefined}>
                  {rodape[c.chave] !== undefined ? formatarCelula(rodape[c.chave], c) : ''}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

/** Tabela "gêmea" de um gráfico, aberta sob demanda. */
export function TabelaDobravel({ titulo = 'Ver os valores em tabela', ...resto }) {
  const [aberta, setAberta] = useState(false);
  return (
    <details className="dobravel" onToggle={(e) => setAberta(e.currentTarget.open)}>
      <summary>{titulo}</summary>
      {aberta && <Tabela compacta {...resto} />}
    </details>
  );
}

/* ------------------------------------------------------------------ */
/* Seção de gráfico                                                   */
/* ------------------------------------------------------------------ */

export function BlocoGrafico({ titulo, nota, children, carregando }) {
  return (
    <section className={`grafico${carregando ? ' esmaecido' : ''}`}>
      <header className="grafico__cabecalho">
        <h3 className="grafico__titulo">{titulo}</h3>
        {nota && <p className="grafico__nota">{nota}</p>}
      </header>
      {children}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Controles                                                          */
/* ------------------------------------------------------------------ */

export function Segmentado({ rotulo, opcoes, valor, aoMudar }) {
  return (
    <div className="segmentado" role="group" aria-label={rotulo}>
      {opcoes.map((o) => (
        <button
          key={o.id}
          type="button"
          className="segmentado__opcao"
          aria-pressed={valor === o.id}
          onClick={() => aoMudar(o.id)}
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}

export function Campo({ rotulo, dica, children, largura, grupo = false }) {
  const id = useId();
  return (
    <div className="campo" style={largura ? { width: largura } : undefined}>
      {grupo ? (
        <span className="campo__rotulo" aria-hidden="true">{rotulo}</span>
      ) : (
        <label className="campo__rotulo" htmlFor={id}>{rotulo}</label>
      )}
      {typeof children === 'function' ? children(id) : children}
      {dica && <span className="campo__dica">{dica}</span>}
    </div>
  );
}

/** Campo numérico que só confirma o valor ao sair do campo ou apertar Enter. */
export function CampoNumero({ rotulo, valor, aoMudar, min, max, passo = 'any', dica, unidade }) {
  const [texto, setTexto] = useState(String(valor));
  useEffect(() => setTexto(String(valor)), [valor]);
  const confirmar = () => {
    const n = Number(String(texto).replace(',', '.'));
    if (Number.isFinite(n) && (min === undefined || n >= min) && (max === undefined || n <= max)) aoMudar(n);
    else setTexto(String(valor));
  };
  return (
    <Campo rotulo={rotulo} dica={dica}>
      {(id) => (
        <div className="entrada-unidade">
          <input
            id={id}
            className="entrada"
            inputMode="decimal"
            value={texto}
            min={min}
            max={max}
            step={passo}
            onChange={(e) => setTexto(e.target.value)}
            onBlur={confirmar}
            onKeyDown={(e) => e.key === 'Enter' && confirmar()}
          />
          {unidade && <span className="entrada-unidade__sufixo">{unidade}</span>}
        </div>
      )}
    </Campo>
  );
}

/* ------------------------------------------------------------------ */
/* Barra de período (filtro único acima do conteúdo)                  */
/* ------------------------------------------------------------------ */

export function BarraPeriodo({ periodo, presets, escolherPreset, escolherIntervalo, children }) {
  const { meta, erro: erroMeta, atualizar, atualizando } = useMeta();
  const [ini, setIni] = useState(periodo?.inicio ?? '');
  const [fim, setFim] = useState(periodo?.fim ?? '');
  useEffect(() => {
    setIni(periodo?.inicio ?? '');
    setFim(periodo?.fim ?? '');
  }, [periodo?.inicio, periodo?.fim]);

  const minimo = meta?.limites?.inicio?.slice(0, 10);
  const aplicar = (a, b) => {
    if (a && b && /^\d{4}-\d{2}-\d{2}$/.test(a) && /^\d{4}-\d{2}-\d{2}$/.test(b)) {
      escolherIntervalo(a <= b ? a : b, a <= b ? b : a);
    }
  };

  return (
    <div className="filtros" role="search" aria-label="Período">
      <div className="filtros__linha">
        <Segmentado rotulo="Período rápido" opcoes={presets} valor={periodo?.preset} aoMudar={escolherPreset} />
        <div className="filtros__datas">
          <label className="filtros__data">
            <span className="visualmente-oculto">Data inicial</span>
            <input
              type="date"
              className="entrada"
              value={ini}
              min={minimo}
              onChange={(e) => {
                setIni(e.target.value);
                aplicar(e.target.value, fim);
              }}
            />
          </label>
          <span aria-hidden="true">a</span>
          <label className="filtros__data">
            <span className="visualmente-oculto">Data final</span>
            <input
              type="date"
              className="entrada"
              value={fim}
              min={minimo}
              onChange={(e) => {
                setFim(e.target.value);
                aplicar(ini, e.target.value);
              }}
            />
          </label>
        </div>
        {children}
      </div>
      <SituacaoDados meta={meta} atualizar={atualizar} atualizando={atualizando} />
      {erroMeta && !meta && (
        <Aviso
          tipo="erro"
          titulo="A API não respondeu"
          acao={
            <button type="button" className="botao" onClick={() => window.location.reload()}>
              Tentar de novo
            </button>
          }
        >
          {erroMeta.message}
        </Aviso>
      )}
    </div>
  );
}

function SituacaoDados({ meta, atualizar, atualizando }) {
  if (!meta) return null;
  const atual = meta.ano_atual ?? {};
  const fim = meta.limites?.fim;
  const aoVivo = atual.origem === 'ao_vivo';
  return (
    <p className="situacao">
      <span>
        Dados até <strong>{dataHoraBR(fim)}</strong>
        {aoVivo
          ? `, baixados do site da ESALQ às ${dataHoraBR(atual.atualizado_em).slice(11)}.`
          : '. O site da ESALQ não respondeu agora; mostrando a última cópia salva.'}
      </span>
      <button type="button" className="botao botao--texto" onClick={atualizar} disabled={atualizando}>
        {atualizando ? 'Buscando…' : 'Buscar dados novos'}
      </button>
    </p>
  );
}

/* ------------------------------------------------------------------ */
/* Cabeçalho de página                                                */
/* ------------------------------------------------------------------ */

export function CabecalhoPagina({ titulo, children }) {
  return (
    <header className="pagina__cabecalho">
      <h1 className="pagina__titulo">{titulo}</h1>
      {children && <p className="pagina__lead">{children}</p>}
    </header>
  );
}

export function Carregando({ texto = 'Carregando…' }) {
  return <p className="carregando" role="status">{texto}</p>;
}
