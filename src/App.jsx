import { useEffect } from 'react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router';
import { ProvedorMeta } from './meta.jsx';
import { buscaDoPeriodo } from './periodo.js';
import Balanco from './paginas/Balanco.jsx';
import Dados from './paginas/Dados.jsx';
import Eventos from './paginas/Eventos.jsx';
import Metodos from './paginas/Metodos.jsx';
import Painel from './paginas/Painel.jsx';
import Postos from './paginas/Postos.jsx';
import Relatorios from './paginas/Relatorios.jsx';

// Páginas que compartilham o mesmo período (levam ?p= / ?inicio=&fim= ao navegar)
const ROTAS = [
  { caminho: '/', rotulo: 'Painel', periodo: true, titulo: 'Painel' },
  { caminho: '/dados', rotulo: 'Dados', periodo: true, titulo: 'Dados de 15 minutos' },
  { caminho: '/eventos', rotulo: 'Eventos de chuva', periodo: true, titulo: 'Eventos de chuva' },
  { caminho: '/relatorios', rotulo: 'Relatórios', periodo: true, titulo: 'Relatórios' },
  { caminho: '/balanco', rotulo: 'Balanço hídrico', titulo: 'Balanço hídrico' },
  { caminho: '/postos', rotulo: 'Postos de SP', titulo: 'Postos de SP' },
  { caminho: '/metodos', rotulo: 'Métodos', titulo: 'Métodos e fontes' },
];

export default function App() {
  const local = useLocation();
  const atual = ROTAS.find((r) => r.caminho === local.pathname);

  useEffect(() => {
    document.title = atual ? `${atual.titulo} – Chuva e balanço hídrico ESALQ` : 'Chuva e balanço hídrico ESALQ';
  }, [atual]);

  return (
    <ProvedorMeta>
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
            Chuva e balanço hídrico
          </Link>
          <span className="topo__sub">Estação automática da ESALQ/USP e postos do INMET em SP</span>
        </div>
        <nav className="topo__nav" aria-label="Páginas">
          <ul>
            {ROTAS.map((r) => (
              <li key={r.caminho}>
                <NavLink
                  to={{ pathname: r.caminho, search: r.periodo ? buscaDoPeriodo(local.search) : '' }}
                  end={r.caminho === '/'}
                  className="topo__link"
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
          <Route path="/" element={<Painel />} />
          <Route path="/dados" element={<Dados />} />
          <Route path="/eventos" element={<Eventos />} />
          <Route path="/relatorios" element={<Relatorios />} />
          <Route path="/balanco" element={<Balanco />} />
          <Route path="/postos" element={<Postos />} />
          <Route path="/metodos" element={<Metodos />} />
          <Route path="*" element={<NaoEncontrada />} />
        </Routes>
      </main>

      <footer className="rodape">
        <p>
          Dados: estação automática do LEB/ESALQ/USP, INMET e NASA POWER. Cálculos descritos em{' '}
          <Link to="/metodos">Métodos</Link>; API em <a href="/api/docs">/api/docs</a>.
        </p>
        <p>
          <a href="https://github.com/rafaelasimion/analise-intensidade-chuva" target="_blank" rel="noreferrer">
            Código no GitHub
          </a>
        </p>
      </footer>
    </ProvedorMeta>
  );
}

function NaoEncontrada() {
  return (
    <div className="pagina">
      <header className="pagina__cabecalho">
        <h1 className="pagina__titulo">Página não encontrada</h1>
        <p className="pagina__lead">
          Esse endereço não existe. Volte para o <Link to="/">painel da estação</Link>.
        </p>
      </header>
    </div>
  );
}
