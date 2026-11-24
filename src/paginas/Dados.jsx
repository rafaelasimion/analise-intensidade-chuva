import { useEffect, useState } from 'react';
import { useApi } from '../api.js';
import { colunasDe } from '../colunas.js';
import { Aviso, BarraPeriodo, Carregando, IntroAba, Tabela } from '../componentes/Comuns.jsx';
import Downloads from '../componentes/Downloads.jsx';
import { num } from '../formato.js';
import { textosResolucao, useMeta } from '../meta.jsx';
import { usePeriodo } from '../periodo.js';

const POR_PAGINA = 100;

function dias({ inicio, fim }) {
  return (Date.parse(fim) - Date.parse(inicio)) / 86400000 + 1;
}

export default function Dados() {
  const { periodo, escolherPreset, escolherIntervalo, presets } = usePeriodo('7d');
  const { versao, api, posto } = useMeta();
  const textos = textosResolucao(posto?.resolucao_min);
  const semRegistros = posto && !posto.tem_registros;
  // limite para o .xlsx (~300 mil linhas): 8 anos de 15 min ou 30 de dados horários
  const limiteXlsx = posto?.resolucao_min === 60 ? 12000 : 3000;
  const [soChuva, setSoChuva] = useState(false);
  const [ordem, setOrdem] = useState('desc');
  const [pagina, setPagina] = useState(1);

  useEffect(() => setPagina(1), [periodo?.inicio, periodo?.fim, soChuva, ordem]);

  const params = periodo
    ? { inicio: periodo.inicio, fim: periodo.fim, pagina, por_pagina: POR_PAGINA, so_chuva: soChuva, ordem, v: versao }
    : null;
  const { dados, erro, carregando } = useApi(`${api}/dados`, params, Boolean(periodo) && !semRegistros);

  return (
    <div className="pagina">
      <IntroAba titulo={textos.tituloDados}>
        Cada linha é um intervalo de {textos.intervalo} que termina no horário indicado (hora de Brasília). A intensidade
        é a chuva do intervalo dividida pela duração, em mm/h.
      </IntroAba>

      <BarraPeriodo periodo={periodo} presets={presets} escolherPreset={escolherPreset} escolherIntervalo={escolherIntervalo}>
        <label className="check">
          <input type="checkbox" checked={soChuva} onChange={(e) => setSoChuva(e.target.checked)} />
          Só registros com chuva
        </label>
        <label className="campo campo--linha">
          <span className="campo__rotulo">Ordem</span>
          <select className="entrada" value={ordem} onChange={(e) => setOrdem(e.target.value)}>
            <option value="desc">Mais recentes primeiro</option>
            <option value="asc">Mais antigos primeiro</option>
          </select>
        </label>
      </BarraPeriodo>

      {semRegistros && (
        <Aviso tipo="info" titulo="Ainda sem dados horários deste posto">
          Os totais diários já estão na aba Relatórios (com download em CSV e .xlsx). Os registros horários entram na
          próxima atualização automática.
        </Aviso>
      )}

      {periodo && !semRegistros && (
        <section className="secao" aria-labelledby="titulo-baixar">
          <h2 id="titulo-baixar" className="secao__titulo">Baixar este período</h2>
          <Downloads
            caminho={`${api}/download`}
            params={{ tipo: 'dados', inicio: periodo.inicio, fim: periodo.fim, so_chuva: soChuva }}
            xlsx={dias(periodo) <= limiteXlsx}
          />
          {dias(periodo) > limiteXlsx && (
            <p className="texto-pequeno">Para um período tão longo, use o CSV: o Excel não abre tantas linhas.</p>
          )}
        </section>
      )}

      {erro && (
        <Aviso tipo="erro" titulo="Não foi possível carregar os dados">
          {erro.message}
        </Aviso>
      )}
      {!dados && !erro && !semRegistros && <Carregando />}

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
                legenda={textos.tituloDados}
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
