import { useEffect, useState } from 'react';
import { useApi } from '../api.js';
import { colunasDe } from '../colunas.js';
import { Aviso, BarraPeriodo, CabecalhoPagina, Carregando, Tabela } from '../componentes/Comuns.jsx';
import Downloads from '../componentes/Downloads.jsx';
import { num } from '../formato.js';
import { useMeta } from '../meta.jsx';
import { usePeriodo } from '../periodo.js';

const POR_PAGINA = 100;

function dias({ inicio, fim }) {
  return (Date.parse(fim) - Date.parse(inicio)) / 86400000 + 1;
}

export default function Dados() {
  const { periodo, escolherPreset, escolherIntervalo, presets } = usePeriodo('7d');
  const { versao } = useMeta();
  const [soChuva, setSoChuva] = useState(false);
  const [ordem, setOrdem] = useState('desc');
  const [pagina, setPagina] = useState(1);

  useEffect(() => setPagina(1), [periodo?.inicio, periodo?.fim, soChuva, ordem]);

  const params = periodo
    ? { inicio: periodo.inicio, fim: periodo.fim, pagina, por_pagina: POR_PAGINA, so_chuva: soChuva, ordem, v: versao }
    : null;
  const { dados, erro, carregando } = useApi('/api/esalq/dados', params, Boolean(periodo));

  return (
    <div className="pagina">
      <CabecalhoPagina titulo="Dados de 15 minutos">
        Cada linha é um intervalo de 15 minutos que termina no horário indicado. A intensidade é a chuva do intervalo
        dividida pela duração, em mm/h.
      </CabecalhoPagina>

      <BarraPeriodo periodo={periodo} presets={presets} escolherPreset={escolherPreset} escolherIntervalo={escolherIntervalo}>
        <label className="check">
          <input type="checkbox" checked={soChuva} onChange={(e) => setSoChuva(e.target.checked)} />
          Só intervalos com chuva
        </label>
        <label className="campo campo--linha">
          <span className="campo__rotulo">Ordem</span>
          <select className="entrada" value={ordem} onChange={(e) => setOrdem(e.target.value)}>
            <option value="desc">Mais recentes primeiro</option>
            <option value="asc">Mais antigos primeiro</option>
          </select>
        </label>
      </BarraPeriodo>

      {periodo && (
        <section className="secao" aria-labelledby="titulo-baixar">
          <h2 id="titulo-baixar" className="secao__titulo">Baixar este período</h2>
          <Downloads
            caminho="/api/esalq/download"
            params={{ tipo: 'dados', inicio: periodo.inicio, fim: periodo.fim, so_chuva: soChuva }}
            xlsx={dias(periodo) <= 3000}
          />
          {dias(periodo) > 3000 && (
            <p className="texto-pequeno">Para mais de 8 anos de dados de 15 min, use o CSV: o Excel não abre tantas linhas.</p>
          )}
        </section>
      )}

      {erro && (
        <Aviso tipo="erro" titulo="Não foi possível carregar os dados">
          {erro.message}
        </Aviso>
      )}
      {!dados && !erro && <Carregando />}

      {dados && (
        <section className={`secao${carregando ? ' esmaecido' : ''}`} aria-labelledby="titulo-registros">
          <h2 id="titulo-registros" className="secao__titulo">
            {num(dados.total, 0)} {dados.total === 1 ? 'registro' : 'registros'}
          </h2>
          {dados.total === 0 ? (
            <Aviso tipo="info" titulo="Nenhum registro">
              {soChuva ? 'Não choveu neste período.' : 'Não há dados neste período.'}
            </Aviso>
          ) : (
            <>
              <Tabela
                legenda="Registros de 15 minutos"
                colunas={colunasDe(dados.colunas, { chuva_mm: { casas: 2 }, intensidade_mm_h: { casas: 2 }, chuva_acum_dia_mm: { casas: 2 } })}
                linhas={dados.linhas}
              />
              <nav className="paginacao" aria-label="Páginas da tabela">
                <button type="button" className="botao" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                  Página anterior
                </button>
                <span>
                  Página {pagina} de {dados.paginas}
                </span>
                <button
                  type="button"
                  className="botao"
                  disabled={pagina >= dados.paginas}
                  onClick={() => setPagina((p) => p + 1)}
                >
                  Próxima página
                </button>
              </nav>
            </>
          )}
        </section>
      )}
    </div>
  );
}
