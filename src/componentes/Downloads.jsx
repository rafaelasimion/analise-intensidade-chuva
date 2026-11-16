import { useState } from 'react';
import { urlApi } from '../api.js';

/** Botões de download (CSV para R, CSV para Excel, .xlsx) + como abrir no R. */
export default function Downloads({ caminho, params, xlsx = true, variavelR = 'dados', children }) {
  const urlR = urlApi(caminho, { ...params, formato: 'csv_r' });
  const urlExcel = urlApi(caminho, { ...params, formato: 'csv_excel' });
  const urlXlsx = urlApi(caminho, { ...params, formato: 'xlsx' });
  const [copiado, setCopiado] = useState(false);

  const codigo = [
    '# Lendo direto do site (sem baixar):',
    `${variavelR} <- read.csv("${urlR}")`,
    '',
    '# Ou, com o arquivo baixado e o pacote readr (datas já viram data/hora):',
    `${variavelR} <- readr::read_csv("caminho/para/o/arquivo_R.csv")`,
  ].join('\n');

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(codigo);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* navegador sem permissão de área de transferência */
    }
  };

  return (
    <div className="downloads">
      <div className="downloads__botoes">
        <a className="botao botao--primario" href={urlR} download>
          CSV para R
        </a>
        <a className="botao" href={urlExcel} download>
          CSV para Excel
        </a>
        {xlsx && (
          <a className="botao" href={urlXlsx} download>
            Planilha .xlsx
          </a>
        )}
        {children}
      </div>
      <details className="dobravel">
        <summary>Como abrir no R</summary>
        <p className="texto-pequeno">
          O CSV para R usa vírgula como separador, ponto decimal, datas no formato AAAA-MM-DD HH:MM:SS e NA nas falhas.
          O CSV para Excel usa ponto e vírgula e vírgula decimal, como o Excel em português espera.
        </p>
        <div className="codigo">
          <pre>
            <code>{codigo}</code>
          </pre>
          <button type="button" className="botao botao--texto codigo__copiar" onClick={copiar}>
            {copiado ? 'Copiado' : 'Copiar'}
          </button>
        </div>
      </details>
    </div>
  );
}
