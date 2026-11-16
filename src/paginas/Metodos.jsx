import { CabecalhoPagina } from '../componentes/Comuns.jsx';
import { dataHoraBR } from '../formato.js';
import { useMeta } from '../meta.jsx';

export default function Metodos() {
  const { meta } = useMeta();
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
          repositório do projeto.
        </p>
        <p>
          <strong>INMET</strong>: estações automáticas do estado de São Paulo, pelos{' '}
          <a href="https://portal.inmet.gov.br/dadoshistoricos" target="_blank" rel="noreferrer">
            pacotes anuais de dados históricos
          </a>
          , que não exigem cadastro. Os dados horários (em UTC) são convertidos para a hora de Brasília e agregados por dia.
          Um dia só é aceito com pelo menos 18 horas de dados.
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
          Toda segunda-feira um processo automático (GitHub Actions) baixa os arquivos novos da ESALQ e do INMET e publica uma
          nova versão do site.
          {atualizacao.esalq && ` Última atualização da ESALQ: ${dataHoraBR(atualizacao.esalq)}.`}
          {atualizacao.inmet && ` Última atualização do INMET: ${dataHoraBR(atualizacao.inmet)}.`}
        </p>

        <h2>Convenções</h2>
        <ul>
          <li>
            Cada registro de 15 minutos representa o intervalo que <em>termina</em> no horário indicado. O registro de 00:00
            pertence ao dia anterior.
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
          (num intervalo de 15 minutos, 1 mm equivale a 4 mm/h).
        </p>
        <p>
          Um evento de chuva é uma sequência de intervalos com chuva separada da próxima por um período seco escolhido na
          página (6 horas por padrão, inspirado no critério de Wischmeier &amp; Smith, 1978). Para cada evento são calculados
          a duração, o total, a intensidade média (total ÷ duração) e as intensidades máximas em janelas móveis de 15, 30 e
          60 minutos (I15, I30 e I60).
        </p>
        <p>
          As máximas anuais são as maiores chuvas de cada ano em janelas móveis de 15 minutos a 24 horas, a série usual para
          ajustar curvas intensidade-duração-frequência.
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
          <code>{`url <- "${typeof window !== 'undefined' ? window.location.origin : ''}/api/esalq/download?tipo=mensal&formato=csv_r&inicio=2024-01-01&fim=2024-12-31"
mensal <- read.csv(url)`}</code>
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
