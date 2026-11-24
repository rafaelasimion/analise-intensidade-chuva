import { useEffect } from 'react';
import { Link, Navigate, NavLink, Route, Routes, useLocation } from 'react-router';
import { NOME_CURTO, SITE } from './config.js';
import { ultimoPosto } from './meta.jsx';
import Balanco from './paginas/Balanco.jsx';
import Comparar from './paginas/Comparar.jsx';
import Dados from './paginas/Dados.jsx';
import Eventos from './paginas/Eventos.jsx';
import Mapa from './paginas/Mapa.jsx';
import Metodos from './paginas/Metodos.jsx';
import Painel from './paginas/Painel.jsx';
import Posto from './paginas/Posto.jsx';
import Relatorios from './paginas/Relatorios.jsx';

const TITULOS = {
  '/': 'Mapa dos postos',
  '/balanco': 'Balanço hídrico',
  '/comparar': 'Comparar postos',
  '/metodos': 'Métodos e fontes',
};

export default function App() {
  const local = useLocation();
  const naPagina = local.pathname.startsWith('/posto/');

  useEffect(() => {
    // As páginas de posto definem o próprio título (com o nome do posto)
    if (naPagina) return;
    const titulo = TITULOS[local.pathname];
    document.title = titulo && local.pathname !== '/' ? `${titulo} – ${NOME_CURTO}` : NOME_CURTO;
  }, [local.pathname, naPagina]);

  const rotas = [
    { caminho: '/', rotulo: 'Mapa dos postos', fim: true },
    { caminho: `/posto/${ultimoPosto()}`, rotulo: 'Painel do posto', ativo: naPagina },
    { caminho: '/balanco', rotulo: 'Balanço hídrico' },
    { caminho: '/comparar', rotulo: 'Comparar postos' },
    { caminho: '/metodos', rotulo: 'Métodos' },
  ];

  return (
    <>
      <a href="#conteudo" className="pular">
        Pular para o conteúdo
      </a>
      <header className="topo">
        <div className="topo__marca">
          <Link to="/" className="topo__nome">
            <svg viewBox="0 0 32 32" className="topo__simbolo" aria-hidden="true">
              <path d="M3 5h26" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <rect x="6" y="5" width="3" height="9" rx="1.5" />
              <rect x="11" y="5" width="3" height="16" rx="1.5" />
              <rect x="16" y="5" width="3" height="6" rx="1.5" />
              <rect x="21" y="5" width="3" height="21" rx="1.5" />
            </svg>
            {SITE.sigla || SITE.nome}
          </Link>
          <span className="topo__sub">{SITE.sigla ? `${SITE.nome}. ${SITE.descricao}` : SITE.descricao}</span>
        </div>
        <nav className="topo__nav" aria-label="Páginas">
          <ul>
            {rotas.map((r) => (
              <li key={r.rotulo}>
                <NavLink
                  to={r.caminho}
                  end={r.fim}
                  className={({ isActive }) => `topo__link${isActive || r.ativo ? ' active' : ''}`}
                  {...(r.ativo ? { 'aria-current': 'page' } : {})}
                >
                  {r.rotulo}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main id="conteudo" className="principal" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Mapa />} />
          <Route path="/posto/:id" element={<Posto />}>
            <Route index element={<Painel />} />
            <Route path="dados" element={<Dados />} />
            <Route path="eventos" element={<Eventos />} />
            <Route path="relatorios" element={<Relatorios />} />
          </Route>
          <Route path="/balanco" element={<Balanco />} />
          <Route path="/comparar" element={<Comparar />} />
          <Route path="/metodos" element={<Metodos />} />
          {/* Endereços da versão anterior (só ESALQ) */}
          <Route path="/painel" element={<Redireciona para="/posto/esalq" />} />
          <Route path="/dados" element={<Redireciona para="/posto/esalq/dados" />} />
          <Route path="/eventos" element={<Redireciona para="/posto/esalq/eventos" />} />
          <Route path="/relatorios" element={<Redireciona para="/posto/esalq/relatorios" />} />
          <Route path="/postos" element={<Redireciona para="/" />} />
          <Route path="*" element={<NaoEncontrada />} />
        </Routes>
      </main>

      <footer className="rodape">
        <p>
          Dados: estação automática do LEB/ESALQ/USP, estações automáticas do INMET e NASA POWER. Cálculos descritos em{' '}
          <Link to="/metodos">Métodos</Link>; API em <a href="/api/docs">/api/docs</a>.
        </p>
        <p>
          <a href="https://github.com/rafaelasimion/analise-intensidade-chuva" target="_blank" rel="noreferrer">
            Código no GitHub
          </a>
        </p>
      </footer>
    </>
  );
}

function Redireciona({ para }) {
  const local = useLocation();
  return <Navigate to={{ pathname: para, search: local.search }} replace />;
}

function NaoEncontrada() {
  return (
    <div className="pagina">
      <header className="pagina__cabecalho">
        <h1 className="pagina__titulo">Página não encontrada</h1>
        <p className="pagina__lead">
          Esse endereço não existe. Volte para o <Link to="/">mapa dos postos</Link>.
        </p>
      </header>
    </div>
  );
}
