import { useApi } from '../api.js';
import { CabecalhoPagina } from '../componentes/Comuns.jsx';
import { dataHoraBR } from '../formato.js';

export default function Metodos() {
  const { dados: meta } = useApi('/api/posto/esalq/meta', {});
  const atualizacao = meta?.atualizacao_repositorio ?? {};
  return (
    <div className="pagina pagina--texto">
      <CabecalhoPagina titulo="Métodos e fontes">
        De onde vêm os dados, como cada número é calculado e como usar os arquivos no R ou no Excel.
      </CabecalhoPagina>

      <section className="texto">
        <h2>Fontes de dados</h2>
        <p>
          <strong>Estação automática da ESALQ/USP</strong> (Departamento de Engenharia de Biossistemas, Piracicaba): registros a
          cada 15 minutos publicados em{' '}
          <a href="https://www.esalq.usp.br/departamentos/leb/automatica/pagina6.html" target="_blank" rel="noreferrer">
            esalq.usp.br/departamentos/leb/automatica
          </a>
          , um arquivo por ano. O ano corrente é baixado do site a cada hora; os anos anteriores ficam guardados no
          repositório do projeto. Os arquivos de 2017 em diante seguem o formato TOA5 (coluna TIMESTAMP); os de 1997 a 2016
          têm um bloco de título, uma legenda com as unidades e colunas de ano, dia juliano e hora, e são lidos pelo mesmo
          programa. Se o intervalo de registro mudar ao longo dos anos (de 1 hora para 15 minutos, por exemplo), cada dia
          usa o seu próprio intervalo.
        </p>
        <p>
          <strong>INMET</strong>: estações automáticas do estado de São Paulo, pelos{' '}
          <a href="https://portal.inmet.gov.br/dadoshistoricos" target="_blank" rel="noreferrer">
            pacotes anuais de dados históricos
          </a>
          , que não exigem cadastro. Os dados horários (em UTC) são convertidos para a hora de Brasília e guardados por
          estação e por ano; os totais diários são calculados a partir deles. Um dia só entra nos totais diários (mapa e
          balanço hídrico) com pelo menos 18 horas de dados. A radiação, que o INMET deixa em branco à noite, é tomada como
          zero entre 19 h e 5 h nos dias em que o sensor funcionou. Estações fora do estado que aparecem no pacote de SP
          (como a C891, na Antártida) são descartadas.
        </p>
        <p>
          O INMET publica os pacotes uma vez por mês, então as estações dele ficam até cerca de um mês atrás da ESALQ, que
          é lida no dia.
        </p>
        <p>
          <strong>NASA POWER</strong>: chuva e temperatura diárias estimadas por satélite e reanálise para qualquer
          coordenada, desde 1981 (
          <a href="https://power.larc.nasa.gov/" target="_blank" rel="noreferrer">
            power.larc.nasa.gov
          </a>
          ). Não são medições do posto; servem quando o posto não tem série suficiente.
        </p>
        <h3>Atualização</h3>
        <p>
          Toda segunda-feira um processo automático (GitHub Actions) baixa os arquivos novos da ESALQ, confere se o INMET
          publicou um pacote novo (só baixa o que mudou) e publica uma nova versão do site.
          {atualizacao.esalq && ` Última atualização da ESALQ: ${dataHoraBR(atualizacao.esalq)}.`}
          {atualizacao.inmet && ` Última atualização do INMET: ${dataHoraBR(atualizacao.inmet)}.`}
        </p>

        <h2>Convenções</h2>
        <ul>
          <li>
            Cada registro (15 minutos na ESALQ, 1 hora no INMET) representa o intervalo que <em>termina</em> no horário
            indicado, em hora de Brasília (UTC−3). O registro de 00:00 pertence ao dia anterior.
          </li>
          <li>Dia com chuva: total diário de pelo menos 1 mm, critério da Organização Meteorológica Mundial.</li>
          <li>
            Limpeza da chuva: valores de erro do sensor (6999, 7999, 9999), valores negativos, mais de 150 mm em 15 minutos e
            picos isolados acima de 100 mm entre registros secos são descartados.
          </li>
          <li>Células vazias e NA nos arquivos indicam falta de dado válido, nunca zero.</li>
        </ul>

        <h2>Intensidade e eventos de chuva</h2>
        <p>
          A intensidade de um intervalo é a chuva dividida pela duração: <span className="formula">I = P ÷ Δt</span>, em mm/h
          (num intervalo de 15 minutos, 1 mm equivale a 4 mm/h; num registro horário, 1 mm é 1 mm/h). Δt é o intervalo de
          registro do posto naquele dia, mesmo depois de uma falha.
        </p>
        <p>
          Um evento de chuva é uma sequência de intervalos com chuva separada da próxima por um período seco escolhido na
          página (6 horas por padrão, inspirado no critério de Wischmeier &amp; Smith, 1978). Para cada evento são calculados
          a duração, o total, a intensidade média (total ÷ duração) e as intensidades máximas em janelas móveis de 15, 30 e
          60 minutos (I15, I30 e I60). Nas estações horárias do INMET a menor janela é de 1 hora, então só existe o I60.
        </p>
        <p>
          As máximas anuais são as maiores chuvas de cada ano em janelas móveis de 15 minutos (ou 1 hora, no INMET) a 24
          horas, a série usual para ajustar curvas intensidade-duração-frequência.
        </p>

        <h2>Mapa</h2>
        <p>
          A cor de cada posto é a chuva total no período, em cinco faixas com cerca de um quinto dos postos cada (quantis
          dos postos com dados em pelo menos 80% dos dias). Postos com menos dias aparecem só com o contorno: o total deles
          está subestimado. No mapa, a ESALQ só conta os dias com pelo menos 80% dos registros de 15 minutos e o INMET, os
          dias com pelo menos 18 horas; por isso o total do mapa pode ficar um pouco abaixo do total do painel do posto,
          que soma todos os registros.
        </p>

        <h2 id="comparacao">Comparação e correlação entre postos</h2>
        <p>
          A comparação calcula o balanço hídrico mensal de cada posto no mesmo período e com a mesma CAD, cada um com as suas
          próprias normais. A correlação é o coeficiente de Pearson (r) entre as séries dos dois postos, só nos dias ou
          meses em que os dois têm dado medido (nada de valores preenchidos): um dia vale se estiver completo, um mês vale se
          tiver dados em pelo menos 90% dos dias. São exigidos pelo menos 30 dias ou 6 meses em comum.
        </p>
        <p>
          A reta de regressão (<span className="formula">y = a + b·x</span>, mínimos quadrados) mostrada para cada par é a
          base do preenchimento de falhas por regressão linear: estima a chuva de um posto a partir do vizinho. Use com
          postos próximos e r alto; a chuva diária costuma ter r bem menor que a mensal, porque a mensal carrega o ciclo das
          estações.
        </p>

        <h2>Balanço hídrico</h2>
        <p>
          Balanço climatológico de Thornthwaite &amp; Mather (1955), no passo mensal ou diário, com a evapotranspiração
          potencial (ETP) de Thornthwaite (1948), como nas planilhas de Rolim, Sentelhas &amp; Barbieri (1998):
        </p>
        <ul className="formulas">
          <li>
            <span className="formula">I = Σ (0,2·Tn)<sup>1,514</sup></span>, com Tn as temperaturas normais de cada mês
          </li>
          <li>
            <span className="formula">a = 6,75·10<sup>−7</sup>·I³ − 7,71·10<sup>−5</sup>·I² + 1,7912·10<sup>−2</sup>·I + 0,49239</span>
          </li>
          <li>
            <span className="formula">ETp = 16·(10·T/I)<sup>a</sup></span> para 0 &lt; T &lt; 26,5 °C e{' '}
            <span className="formula">ETp = −415,85 + 32,24·T − 0,43·T²</span> para T ≥ 26,5 °C (Willmott et al., 1985)
          </li>
          <li>
            <span className="formula">ETP = ETp·(N/12)·(NDP/30)</span>, com N o fotoperíodo do dia 15 do mês (ou de cada dia)
            e NDP o número de dias do período
          </li>
          <li>
            Com <span className="formula">P − ETP &lt; 0</span>:{' '}
            <span className="formula">NEG.AC = NEG.AC<sub>ant</sub> + (P − ETP)</span> e{' '}
            <span className="formula">ARM = CAD·e<sup>NEG.AC/CAD</sup></span>
          </li>
          <li>
            Com <span className="formula">P − ETP ≥ 0</span>: <span className="formula">ARM = mín(ARM<sub>ant</sub> + P − ETP; CAD)</span>
          </li>
          <li>
            <span className="formula">ETR = ETP</span> quando P ≥ ETP; senão <span className="formula">ETR = P − ALT</span>.
            DEF = ETP − ETR; EXC = (P − ETP) − ALT quando o solo está na CAD.
          </li>
        </ul>
        <p>
          As normais (médias de cada mês) usam o próprio período quando ele cobre os 12 meses; em períodos curtos, usam toda a
          série do posto. O armazenamento inicial vem do balanço normal no mês anterior ao início. Dias sem chuva registrada
          são completados com a média diária normal do mês e dias sem temperatura, com a normal do mês; a página avisa
          quantos foram estimados. O clima é classificado pelo índice hídrico de Thornthwaite (1948),{' '}
          <span className="formula">Im = Ih − 0,6·Ia</span>.
        </p>

        <h2>Arquivos e API</h2>
        <p>
          <strong>CSV para R</strong>: vírgula como separador, ponto decimal, datas ISO (AAAA-MM-DD HH:MM:SS), NA nas falhas e
          nomes de colunas sem acento (chuva_mm, intensidade_mm_h, vento_ms…). Abre com <code>read.csv()</code> ou{' '}
          <code>readr::read_csv()</code>. <strong>CSV para Excel</strong>: ponto e vírgula, vírgula decimal e cabeçalhos em
          português.
        </p>
        <p>
          Todos os números do site vêm de uma API pública. A documentação interativa, com todos os parâmetros, está em{' '}
          <a href="/api/docs">/api/docs</a>. Exemplo no R:
        </p>
        <pre className="codigo">
          <code>{`url <- "${typeof window !== 'undefined' ? window.location.origin : ''}/api/posto/esalq/download?tipo=mensal&formato=csv_r&inicio=2024-01-01&fim=2024-12-31"
mensal <- read.csv(url)

# Qualquer posto: troque "esalq" pelo id do posto (ex.: inmet-A711, de São Carlos)
horario <- read.csv("${typeof window !== 'undefined' ? window.location.origin : ''}/api/posto/inmet-A711/download?tipo=dados&formato=csv_r&inicio=2025-01-01&fim=2025-01-31")`}</code>
        </pre>

        <h2>Referências</h2>
        <ul className="referencias">
          <li>
            PEREIRA, A. R.; ANGELOCCI, L. R.; SENTELHAS, P. C. <em>Agrometeorologia: fundamentos e aplicações práticas</em>.
            Guaíba: Agropecuária, 2002.
          </li>
          <li>
            ROLIM, G. S.; SENTELHAS, P. C.; BARBIERI, V. Planilhas no ambiente Excel para os cálculos de balanços hídricos:
            normal, seqüencial, de cultura e de produtividade real e potencial. <em>Revista Brasileira de Agrometeorologia</em>,
            v. 6, n. 1, p. 133–137, 1998.
          </li>
          <li>
            THORNTHWAITE, C. W. An approach toward a rational classification of climate. <em>Geographical Review</em>, v. 38,
            n. 1, p. 55–94, 1948.
          </li>
          <li>
            THORNTHWAITE, C. W.; MATHER, J. R. <em>The water balance</em>. Centerton: Drexel Institute of Technology, 1955.
            (Publications in Climatology, v. 8, n. 1).
          </li>
          <li>
            WILLMOTT, C. J.; ROWE, C. M.; MINTZ, Y. Climatology of the terrestrial seasonal water cycle.{' '}
            <em>Journal of Climatology</em>, v. 5, p. 589–606, 1985.
          </li>
          <li>
            WISCHMEIER, W. H.; SMITH, D. D. <em>Predicting rainfall erosion losses</em>. Washington: USDA, 1978. (Agriculture
            Handbook, 537).
          </li>
        </ul>
      </section>
    </div>
  );
}
