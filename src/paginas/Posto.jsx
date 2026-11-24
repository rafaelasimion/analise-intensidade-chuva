import { useEffect } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router';
import { Aviso, Campo } from '../componentes/Comuns.jsx';
import { NOME_CURTO } from '../config.js';
import { dataBR } from '../formato.js';
import { ProvedorPosto, useMeta } from '../meta.jsx';
import { buscaDoPeriodo, diaDoRegistro } from '../periodo.js';
import { descricaoPosto, nomePosto, ordenarParaLista, usePostos } from '../postos.js';

const ABAS = [
  { caminho: '', rotulo: 'Painel' },
  { caminho: 'dados', rotulo: 'Dados' },
  { caminho: 'eventos', rotulo: 'Eventos de chuva' },
  { caminho: 'relatorios', rotulo: 'Relatórios' },
];

/** Página de um posto: cabeçalho com o nome, troca de posto e abas. */
export default function Posto() {
  const { id } = useParams();
  return (
    <ProvedorPosto id={id}>
      <div className="pagina">
        <CabecalhoPosto />
        {/* key: ao trocar de posto, as abas recomeçam (filtros, página da tabela…) */}
        <Outlet key={id} />
      </div>
    </ProvedorPosto>
  );
}

function CabecalhoPosto() {
  const { id, meta, erro, posto } = useMeta();
  const { dados } = usePostos();
  const local = useLocation();
  const navegar = useNavigate();
  const aba = local.pathname.split('/')[3] ?? '';
  const rotuloAba = ABAS.find((a) => a.caminho === aba)?.rotulo ?? 'Painel';
  const atual = posto?.id ?? id;

  useEffect(() => {
    if (posto) document.title = `${rotuloAba} – ${nomePosto(posto)} – ${NOME_CURTO}`;
  }, [posto, rotuloAba]);

  const trocar = (novo) =>
    navegar({ pathname: `/posto/${novo}${aba ? `/${aba}` : ''}`, search: buscaDoPeriodo(local.search) });

  const lista = ordenarParaLista(dados?.postos);
  const limites = meta?.limites;

  return (
    <header className="posto-topo">
      <div className="posto-topo__linha">
        <div className="posto-topo__identidade">
          <p className="posto-topo__rede">{posto ? descricaoPosto(posto) : ' '}</p>
          <h1 className="pagina__titulo posto-topo__nome">
            {posto ? nomePosto(posto) : erro ? 'Posto não encontrado' : 'Carregando o posto…'}
          </h1>
          {limites?.inicio && (
            <p className="posto-topo__periodo">
              Dados de {dataBR(limites.inicio)} a {dataBR(diaDoRegistro(limites.fim))}
              {posto?.municipio && posto.fonte !== 'esalq' ? `, em ${posto.municipio}` : ''}.
            </p>
          )}
        </div>
        <div className="posto-topo__acoes">
          <Campo rotulo="Trocar de posto">
            {(cid) => (
              <select id={cid} className="entrada entrada--larga" value={atual} onChange={(e) => trocar(e.target.value)}>
                {!lista.some((p) => p.id === atual) && <option value={atual}>{posto ? nomePosto(posto) : atual}</option>}
                {lista.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.fonte === 'esalq' ? 'ESALQ/USP – Piracicaba' : `${p.nome} (${p.codigo})`}
                  </option>
                ))}
              </select>
            )}
          </Campo>
          {posto && (
            <p className="posto-topo__links">
              <Link to={`/balanco?posto=${posto.codigo}`}>Balanço hídrico</Link>
              <Link to={`/comparar?postos=${posto.id}`}>Comparar com outros postos</Link>
              <Link to={`/?posto=${posto.id}`}>Ver no mapa</Link>
            </p>
          )}
        </div>
      </div>

      <nav className="abas" aria-label="Seções do posto">
        <ul>
          {ABAS.map((a) => (
            <li key={a.rotulo}>
              <NavLink
                to={{ pathname: `/posto/${id}${a.caminho ? `/${a.caminho}` : ''}`, search: buscaDoPeriodo(local.search) }}
                end
                className="abas__link"
              >
                {a.rotulo}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {erro && !meta && (
        <Aviso tipo="erro" titulo="Não foi possível abrir este posto">
          {erro.message} Escolha outro posto na lista acima ou no <Link to="/">mapa</Link>.
        </Aviso>
      )}
      {meta?.aviso && (
        <Aviso tipo="info" titulo="Só os totais diários por enquanto">
          Os dados horários desta estação entram no site na próxima atualização automática (veja{' '}
          <Link to="/metodos">Métodos</Link>). Até lá, o painel e os relatórios usam os totais diários.
        </Aviso>
      )}
    </header>
  );
}
