import { useEffect, useRef, useState } from 'react';
import contorno from '../dados/sp.json';

/* Contorno do estado projetado em coordenadas planas (equirretangular com correção do cosseno da latitude). */
const GEOM = contorno.features[0].geometry;
const ANEIS = GEOM.type === 'Polygon' ? [GEOM.coordinates] : GEOM.coordinates;
const TODOS = ANEIS.flat(2);
const LON_MIN = Math.min(...TODOS.map((c) => c[0]));
const LON_MAX = Math.max(...TODOS.map((c) => c[0]));
const LAT_MIN = Math.min(...TODOS.map((c) => c[1]));
const LAT_MAX = Math.max(...TODOS.map((c) => c[1]));
const KX = Math.cos((((LAT_MIN + LAT_MAX) / 2) * Math.PI) / 180);
const ESCALA = 100;
const MARGEM = 18;
export const LARGURA = (LON_MAX - LON_MIN) * KX * ESCALA + 2 * MARGEM;
export const ALTURA = (LAT_MAX - LAT_MIN) * ESCALA + 2 * MARGEM;

export function projetar(lon, lat) {
  return [(lon - LON_MIN) * KX * ESCALA + MARGEM, (LAT_MAX - lat) * ESCALA + MARGEM];
}

const CAMINHO = ANEIS.map((poligono) =>
  poligono
    .map((anel) => anel.map(([lon, lat], i) => `${i ? 'L' : 'M'}${projetar(lon, lat).map((v) => v.toFixed(1)).join(',')}`).join('') + 'Z')
    .join(''),
).join('');

export function dentroDoMapa(p) {
  return p.lat <= LAT_MAX + 0.3 && p.lat >= LAT_MIN - 0.3 && p.lon >= LON_MIN - 0.3 && p.lon <= LON_MAX + 0.3;
}

const sobrepoe = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];

/**
 * Posição dos rótulos sem sobreposição: tenta à direita, à esquerda, acima e abaixo
 * do marcador; se nenhuma couber, o rótulo fica de fora (o nome aparece na dica).
 */
function posicionarRotulos(postos, px, raio) {
  const fonte = 14 * px;
  const caixas = [];
  const saida = [];
  for (const p of postos) {
    const [x, y] = projetar(p.lon, p.lat);
    const w = p.rotulo.length * fonte * 0.58;
    const h = fonte * 1.15;
    const d = raio + 8 * px;
    const opcoes = {
      direita: { x: x + d, y: y + fonte * 0.35, ancora: 'start', caixa: [x + d, y - h / 2, x + d + w, y + h / 2] },
      esquerda: { x: x - d, y: y + fonte * 0.35, ancora: 'end', caixa: [x - d - w, y - h / 2, x - d, y + h / 2] },
      acima: { x, y: y - d, ancora: 'middle', caixa: [x - w / 2, y - d - h, x + w / 2, y - d] },
      abaixo: { x, y: y + d + fonte * 0.8, ancora: 'middle', caixa: [x - w / 2, y + d, x + w / 2, y + d + h] },
    };
    const ordem = x > LARGURA * 0.62 ? ['esquerda', 'direita', 'acima', 'abaixo'] : ['direita', 'esquerda', 'acima', 'abaixo'];
    const livre = ordem
      .map((k) => opcoes[k])
      .find((o) => o.caixa[0] >= 0 && o.caixa[2] <= LARGURA && o.caixa[1] >= 0 && !caixas.some((c) => sobrepoe(c, o.caixa)));
    if (livre) {
      caixas.push(livre.caixa);
      saida.push({ p, ...livre });
    }
  }
  return saida;
}

/** Largura do elemento na tela (para manter os marcadores do mesmo tamanho em qualquer tela). */
function useLargura(ref) {
  const [largura, setLargura] = useState(800);
  useEffect(() => {
    if (!ref.current) return undefined;
    const obs = new ResizeObserver(([e]) => setLargura(e.contentRect.width || 800));
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, [ref]);
  return largura;
}

/**
 * Mapa dos postos em SVG.
 *
 * postos: [{ id, lat, lon, cor, vazio, incompleto, rotulo, esalq }]
 *   cor        – preenchimento (classe de chuva) ou null
 *   vazio      – sem dados no período (círculo vazado cinza)
 *   incompleto – dados em menos dias que o mínimo (anel na cor da classe)
 * dica(p): conteúdo (JSX) da dica ao passar o mouse ou focar.
 */
export default function MapaSP({ postos, selecionados = [], aoSelecionar, dica, rotuloAcessivel, rotulosFixos = false }) {
  const figura = useRef(null);
  const largura = useLargura(figura);
  const [foco, setFoco] = useState(null);
  const px = LARGURA / Math.max(largura, 1); // unidades do SVG por pixel de tela
  const raio = 7 * px;
  const alvo = Math.max(14 * px, raio + 4 * px);

  const visiveis = postos.filter(dentroDoMapa);
  // Selecionados e ESALQ por cima
  const ordem = [...visiveis].sort(
    (a, b) => (selecionados.includes(a.id) - selecionados.includes(b.id)) || (a.esalq - b.esalq),
  );
  const ativo = visiveis.find((p) => p.id === foco);
  const rotulados = posicionarRotulos(
    (rotulosFixos ? selecionados : selecionados.slice(0, 1))
      .map((id) => visiveis.find((p) => p.id === id))
      .filter(Boolean),
    px,
    raio * 1.3,
  );

  const marcador = (p) => {
    const marcado = selecionados.includes(p.id);
    const r = marcado ? raio * 1.3 : raio;
    const estilo = p.vazio
      ? { fill: 'var(--folha)', stroke: 'var(--borda-campo)', strokeWidth: 1.5 * px }
      : p.incompleto
        ? { fill: 'var(--folha)', stroke: p.cor, strokeWidth: 3 * px }
        : { fill: p.cor, stroke: 'var(--folha)', strokeWidth: 2 * px };
    const forma = p.esalq ? (
      <rect x={-r} y={-r} width={2 * r} height={2 * r} rx={2 * px} transform="rotate(45)" style={estilo} />
    ) : (
      <circle r={p.vazio ? r * 0.75 : r} style={estilo} />
    );
    return (
      <g
        key={p.id}
        className={`mapa-sp__posto${marcado ? ' mapa-sp__posto--marcado' : ''}`}
        transform={`translate(${projetar(p.lon, p.lat).map((v) => v.toFixed(1)).join(',')})`}
        tabIndex={0}
        role="button"
        aria-pressed={marcado}
        aria-label={p.rotuloAcessivel ?? p.rotulo}
        onMouseEnter={() => setFoco(p.id)}
        onMouseLeave={() => setFoco(null)}
        onFocus={() => setFoco(p.id)}
        onBlur={() => setFoco(null)}
        onClick={() => aoSelecionar?.(p.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            aoSelecionar?.(p.id);
          }
        }}
      >
        <circle r={alvo} className="mapa-sp__alvo" />
        {marcado && <circle r={r + 4.5 * px} className="mapa-sp__anel" style={{ strokeWidth: 2 * px }} />}
        {forma}
      </g>
    );
  };

  const posDica = ativo ? projetar(ativo.lon, ativo.lat) : null;

  return (
    <div className="mapa-sp" ref={figura}>
      <svg
        viewBox={`0 0 ${LARGURA.toFixed(0)} ${ALTURA.toFixed(0)}`}
        className="mapa-sp__svg"
        role="group"
        aria-label={rotuloAcessivel}
      >
        <path d={CAMINHO} className="mapa-sp__estado" style={{ strokeWidth: 1.2 * px }} />
        {ordem.map(marcador)}
        {rotulados.map((r) => (
          <text
            key={`r-${r.p.id}`}
            x={r.x}
            y={r.y}
            textAnchor={r.ancora}
            className="mapa-sp__rotulo"
            style={{ fontSize: 14 * px, strokeWidth: 4 * px }}
            aria-hidden="true"
          >
            {r.p.rotulo}
          </text>
        ))}
      </svg>
      {ativo && dica && (
        <div
          className={`mapa-sp__dica${posDica[0] > LARGURA * 0.55 ? ' mapa-sp__dica--esquerda' : ''}`}
          style={{ left: `${(posDica[0] / LARGURA) * 100}%`, top: `${(posDica[1] / ALTURA) * 100}%` }}
          role="status"
        >
          {dica(ativo)}
        </div>
      )}
    </div>
  );
}
