import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { useApi } from '../api.js';
import { Aviso, CabecalhoPagina, CampoNumero, Carregando, Tabela } from '../componentes/Comuns.jsx';
import contorno from '../dados/sp.json';
import { dataBR, num } from '../formato.js';

function distanciaKm(a, b) {
  const R = 6371;
  const rad = (g) => (g * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export default function Postos() {
  const { dados, erro } = useApi('/api/postos', {});
  const [busca, setBusca] = useState('');
  const [ref, setRef] = useState(null);
  const [selecionado, setSelecionado] = useState(null);
  const [erroLocal, setErroLocal] = useState(null);

  const postos = useMemo(() => {
    let lista = dados?.postos ?? [];
    if (busca.trim()) {
      const b = busca.trim().toLowerCase();
      lista = lista.filter((p) => `${p.nome} ${p.codigo} ${p.municipio ?? ''}`.toLowerCase().includes(b));
    }
    if (ref) {
      lista = lista.map((p) => ({ ...p, distancia_km: distanciaKm(ref, p) })).sort((a, b) => a.distancia_km - b.distancia_km);
    }
    return lista;
  }, [dados, busca, ref]);

  const usarLocalizacao = () => {
    setErroLocal(null);
    if (!navigator.geolocation) {
      setErroLocal('Este navegador não informa a localização. Digite a latitude e a longitude.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setRef({ lat: Number(pos.coords.latitude.toFixed(4)), lon: Number(pos.coords.longitude.toFixed(4)) }),
      () => setErroLocal('A localização não foi liberada. Digite a latitude e a longitude.'),
      { timeout: 10000 },
    );
  };

  const comDados = (dados?.postos ?? []).filter((p) => p.tem_dados).length;

  const colunas = [
    {
      chave: 'nome',
      rotulo: 'Posto',
      render: (p) => (
        <span className="posto-nome">
          {p.fonte === 'esalq' ? 'ESALQ/USP – Piracicaba' : p.nome}
          <span className="posto-nome__rede">{p.rede}, {p.tipo.toLowerCase()}</span>
        </span>
      ),
    },
    { chave: 'codigo', rotulo: 'Código', tipo: 'texto' },
    { chave: 'alt', rotulo: 'Altitude (m)', tipo: 'num', casas: 0 },
    {
      chave: 'dados',
      rotulo: 'Dados no site',
      render: (p) => (p.tem_dados ? `${dataBR(p.inicio_dados)} a ${dataBR(p.fim_dados)}` : 'aguardando a atualização'),
    },
    ...(ref ? [{ chave: 'distancia_km', rotulo: 'Distância (km)', tipo: 'num', casas: 0 }] : []),
    {
      chave: 'acoes',
      rotulo: 'Ações',
      render: (p) => (
        <span className="acoes-linha">
          <Link to={`/balanco?posto=${p.codigo}${p.tem_dados ? '' : '&dados=nasa'}`}>Balanço hídrico</Link>
          <a href={`https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=13/${p.lat}/${p.lon}`} target="_blank" rel="noreferrer">
            Mapa
          </a>
        </span>
      ),
    },
  ];

  return (
    <div className="pagina">
      <CabecalhoPagina titulo="Postos meteorológicos de SP">
        A estação da ESALQ e as estações automáticas do INMET no estado. Escolha um posto para calcular o balanço hídrico
        ou ordene a lista pela distância de um local.
      </CabecalhoPagina>

      {erro && <Aviso tipo="erro">{erro.message}</Aviso>}
      {!dados && !erro && <Carregando />}

      {dados && (
        <>
          <div className="filtros" role="search" aria-label="Buscar postos">
            <div className="filtros__linha">
              <label className="campo">
                <span className="campo__rotulo">Buscar</span>
                <input
                  className="entrada entrada--larga"
                  type="search"
                  placeholder="Nome, município ou código"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                />
              </label>
              <CampoNumero
                rotulo="Latitude do local"
                unidade="°"
                valor={ref?.lat ?? ''}
                aoMudar={(v) => setRef((r) => ({ lat: v, lon: r?.lon ?? -47.63 }))}
                min={-34}
                max={6}
              />
              <CampoNumero
                rotulo="Longitude do local"
                unidade="°"
                valor={ref?.lon ?? ''}
                aoMudar={(v) => setRef((r) => ({ lat: r?.lat ?? -22.7, lon: v }))}
                min={-75}
                max={-30}
              />
              <button type="button" className="botao" onClick={usarLocalizacao}>
                Usar minha localização
              </button>
              {ref && (
                <button type="button" className="botao botao--texto" onClick={() => setRef(null)}>
                  Limpar local
                </button>
              )}
            </div>
            <p className="situacao">
              <span>
                {num(dados.postos.length, 0)} postos; {num(comDados, 0)} com dados já baixados para o site. Os demais podem usar o
                NASA POWER até a atualização do INMET rodar.
              </span>
            </p>
          </div>
          {erroLocal && <Aviso tipo="atencao">{erroLocal}</Aviso>}

          <div className="postos">
            <Mapa postos={postos} referencia={ref} selecionado={selecionado} aoSelecionar={setSelecionado} />
            <Tabela
              legenda="Postos meteorológicos"
              colunas={colunas}
              linhas={postos.map((p) => ({ ...p, id: p.id }))}
              destacar={(p) => p.codigo === selecionado}
            />
          </div>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Mapa em SVG (contorno do estado + postos)                          */
/* ------------------------------------------------------------------ */

const GEOM = contorno.features[0].geometry;
const ANEIS = GEOM.type === 'Polygon' ? [GEOM.coordinates] : GEOM.coordinates;
const TODOS = ANEIS.flat(2);
const LON_MIN = Math.min(...TODOS.map((c) => c[0]));
const LON_MAX = Math.max(...TODOS.map((c) => c[0]));
const LAT_MIN = Math.min(...TODOS.map((c) => c[1]));
const LAT_MAX = Math.max(...TODOS.map((c) => c[1]));
const KX = Math.cos((((LAT_MIN + LAT_MAX) / 2) * Math.PI) / 180);
const ESCALA = 50;
const MARGEM = 12;
const LARGURA = (LON_MAX - LON_MIN) * KX * ESCALA + 2 * MARGEM;
const ALTURA = (LAT_MAX - LAT_MIN) * ESCALA + 2 * MARGEM;

function projetar(lon, lat) {
  return [(lon - LON_MIN) * KX * ESCALA + MARGEM, (LAT_MAX - lat) * ESCALA + MARGEM];
}

const CAMINHO = ANEIS.map((poligono) =>
  poligono
    .map((anel) => anel.map(([lon, lat], i) => `${i ? 'L' : 'M'}${projetar(lon, lat).map((v) => v.toFixed(1)).join(',')}`).join('') + 'Z')
    .join(''),
).join('');

function Mapa({ postos, referencia, selecionado, aoSelecionar }) {
  const [foco, setFoco] = useState(null);
  const visiveis = postos
    .filter((p) => p.lat <= LAT_MAX + 0.5 && p.lat >= LAT_MIN - 0.5 && p.lon >= LON_MIN - 0.5 && p.lon <= LON_MAX + 0.5)
    .sort((a, b) => (a.fonte === 'esalq') - (b.fonte === 'esalq'));
  const ativo = visiveis.find((p) => p.codigo === (foco ?? selecionado));

  return (
    <figure className="mapa">
      <svg viewBox={`0 0 ${LARGURA.toFixed(0)} ${ALTURA.toFixed(0)}`} className="mapa__svg" aria-label="Mapa dos postos no estado de São Paulo">
        <path d={CAMINHO} className="mapa__estado" />
        {referencia && (() => {
          const [x, y] = projetar(referencia.lon, referencia.lat);
          return (
            <g className="mapa__referencia" aria-hidden="true">
              <path d={`M${x - 8},${y}H${x + 8}M${x},${y - 8}V${y + 8}`} />
              <circle cx={x} cy={y} r="4" />
            </g>
          );
        })()}
        {visiveis.map((p) => {
          const [x, y] = projetar(p.lon, p.lat);
          const marcado = p.codigo === selecionado || p.codigo === foco;
          const classe = `mapa__posto${p.tem_dados ? ' mapa__posto--dados' : ''}${p.fonte === 'esalq' ? ' mapa__posto--esalq' : ''}${marcado ? ' mapa__posto--marcado' : ''}`;
          return (
            <g
              key={p.id}
              className={classe}
              transform={`translate(${x.toFixed(1)},${y.toFixed(1)})`}
              tabIndex={0}
              role="button"
              aria-label={`${p.nome} (${p.codigo})`}
              onMouseEnter={() => setFoco(p.codigo)}
              onMouseLeave={() => setFoco(null)}
              onFocus={() => setFoco(p.codigo)}
              onBlur={() => setFoco(null)}
              onClick={() => aoSelecionar(p.codigo === selecionado ? null : p.codigo)}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), aoSelecionar(p.codigo))}
            >
              <circle r="12" className="mapa__alvo" />
              {p.fonte === 'esalq' ? <rect x="-5.5" y="-5.5" width="11" height="11" rx="2" transform="rotate(45)" /> : <circle r="5" />}
            </g>
          );
        })}
        {ativo && (() => {
          const [x, y] = projetar(ativo.lon, ativo.lat);
          const esquerda = x > LARGURA * 0.6;
          return (
            <text
              x={esquerda ? x - 12 : x + 12}
              y={y + 4}
              textAnchor={esquerda ? 'end' : 'start'}
              className="mapa__rotulo"
            >
              {ativo.fonte === 'esalq' ? 'ESALQ/USP' : ativo.nome} ({ativo.codigo})
            </text>
          );
        })()}
      </svg>
      <figcaption className="mapa__legenda">
        <span><svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="5" className="legenda-dados" /></svg> INMET com dados no site</span>
        <span><svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" className="legenda-sem" /></svg> INMET aguardando atualização</span>
        <span><svg width="12" height="12" aria-hidden="true"><rect x="2" y="2" width="8" height="8" rx="1.5" transform="rotate(45 6 6)" className="legenda-esalq" /></svg> ESALQ/USP</span>
      </figcaption>
    </figure>
  );
}
