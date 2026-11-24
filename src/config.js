/**
 * Nome do site — troque aqui e ele muda no topo, no título da aba e no index.html.
 *
 * sigla: se preenchida, aparece grande no topo, com o nome completo embaixo
 *        (ex.: sigla 'PLUVIA-SP', nome 'Chuva e balanço hídrico em São Paulo').
 */
export const SITE = {
  sigla: '',
  nome: 'Chuva e balanço hídrico',
  descricao: 'Postos meteorológicos da ESALQ/USP e do INMET no estado de São Paulo',
};

/** Nome usado no título da aba do navegador. */
export const NOME_CURTO = SITE.sigla || SITE.nome;
