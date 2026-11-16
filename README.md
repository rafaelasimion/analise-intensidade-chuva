# 🌧️ Chuva e balanço hídrico – ESALQ e postos de SP

Site para analisar os dados da **estação automática da ESALQ/USP** (Piracicaba) e das **estações automáticas do INMET em São Paulo**: chuva, intensidade (mm/h), temperatura, umidade, vento, eventos de chuva, máximas anuais e balanço hídrico.

Este projeto contou com auxílio de ferramentas de inteligência artificial no desenvolvimento do código. 🤖

## O que o site faz

| Página | O que tem |
|---|---|
| **Painel** | Pluviograma (chuva por intervalo e acumulada), resumo do período, intensidade, temperatura, umidade, vento e chuva por ano |
| **Dados** | Registros de 15 min com intensidade (mm/h) e vento; download em **CSV para R**, CSV para Excel e .xlsx |
| **Eventos de chuva** | Cada chuva com início, fim, duração, total, intensidade média (mm/h), I15, I30 e I60; calculadora de intensidade; máximas anuais por duração (base para curvas IDF) |
| **Relatórios** | Relatório diário, semanal, mensal ou anual, pronto para imprimir/salvar em PDF; **planilha hidrológica** (.xlsx com todas as abas) |
| **Balanço hídrico** | Thornthwaite & Mather (1955) com ETP de Thornthwaite (1948): 1 mês, 1 ano, 5, 10, 20 anos ou período personalizado (mín. 1 mês), passo mensal ou diário, CAD ajustável, balanço normal e classificação climática |
| **Postos de SP** | ESALQ + 42 estações automáticas do INMET, com mapa e ordenação por distância |
| **Métodos** | Fontes, fórmulas, convenções e referências |

## Arquitetura

```
React (Vite)  ──►  /api/*  ──►  FastAPI (função Python da Vercel)  ──►  pandas
   src/                         api/index.py → hidro/ (cálculos)
                                dados/ (séries guardadas no repositório)
```

- **Frontend** (`src/`): React + JavaScript + CSS puro, gráficos com ECharts.
- **Backend** (`api/index.py` + pacote `hidro/`): FastAPI rodando como função serverless da Vercel. Todos os cálculos estão em `hidro/` e não dependem da API (dá para usar em scripts e notebooks).
- **Dados** (`dados/`):
  - `dados/esalq/esalq_AAAA.csv.gz`: dados de 15 min da ESALQ, um arquivo por ano.
  - `dados/inmet/diario/inmet_sp_AAAA.csv.gz`: dados diários das estações do INMET em SP.
  - `dados/inmet/estacoes_sp.json`: lista dos postos.
- O **ano corrente** da ESALQ é baixado ao vivo do site do LEB (cache de 1 h). Se o site estiver fora do ar, o sistema usa a última cópia do repositório.

## Rodar no computador

Requisitos: Python 3.12+ e Node 20+.

```bash
pip install -r requirements-dev.txt
npm install
npm run dev          # site em http://localhost:5173 e API em http://localhost:8000
```

`npm run dev` sobe as duas partes juntas (se o seu Python se chamar `python3`, rode `npm run dev:web` e, em outro terminal, `python3 -m uvicorn api.index:app --reload --port 8000`).

Testes: `python -m pytest`

## Publicar na Vercel

1. Na Vercel, importe este repositório (ou conecte o projeto existente a ele). O `vercel.json` já define tudo: preset **Vite**, função Python em `api/index.py` e região `gru1` (São Paulo).
2. Faça o deploy. Não precisa de variáveis de ambiente.
3. **Uma vez**, rode a atualização completa dos dados: no GitHub, aba **Actions → Atualizar dados → Run workflow** (alvo `tudo`). Ela baixa todos os anos da ESALQ (com temperatura, umidade e vento) e os pacotes do INMET. A primeira vez pode levar perto de uma hora por causa do INMET.

Depois disso, a atualização roda sozinha toda segunda-feira e faz commit dos arquivos novos; a Vercel publica a nova versão automaticamente.

> A versão antiga em Streamlit está em `legado/` (o Streamlit não roda na Vercel). Pode apagar a pasta quando a versão nova estiver no ar.

## Atualizar os dados na mão

```bash
python scripts/atualizar_dados.py esalq                 # anos novos ou incompletos da ESALQ
python scripts/atualizar_dados.py esalq --desde 1997 --forcar
python scripts/atualizar_dados.py inmet --anos 2025 2026
python scripts/atualizar_dados.py tudo
```

O script registra em `dados/esalq/colunas.json` quais colunas encontrou em cada arquivo da ESALQ e como interpretou cada uma (chuva, vento, temperatura…). A mesma informação aparece em `/api/esalq/diagnostico`. Se o nome de alguma coluna mudar, o ajuste é em `hidro/esalq.py` (`_classificar_coluna`).

## Usar no R

Os botões **CSV para R** geram arquivos com vírgula como separador, ponto decimal, datas ISO e `NA` nas falhas. Dá para ler direto da API:

```r
url <- "https://SEU-SITE.vercel.app/api/esalq/download?tipo=dados&formato=csv_r&inicio=2025-01-01&fim=2025-12-31"
dados <- read.csv(url)
```

Tipos disponíveis em `tipo`: `dados` (15 min), `diario`, `semanal`, `mensal`, `anual`, `eventos`, `maximas`. A documentação interativa de todas as rotas fica em `/api/docs`.

## Principais rotas da API

| Rota | Retorna |
|---|---|
| `GET /api/esalq/meta` | anos disponíveis, primeiro/último registro, origem do ano corrente |
| `GET /api/esalq/painel?inicio&fim` | resumo + série para os gráficos |
| `GET /api/esalq/dados?inicio&fim&pagina` | registros de 15 min |
| `GET /api/esalq/eventos?inicio&fim&intervalo_seco_h&chuva_min_mm` | eventos de chuva |
| `GET /api/esalq/relatorio?inicio&fim&escala` | relatório diário/semanal/mensal/anual |
| `GET /api/esalq/maximas?inicio&fim` | máximas anuais por duração |
| `GET /api/esalq/download?tipo&formato` | CSV (R ou Excel) ou .xlsx |
| `GET /api/esalq/planilha?inicio&fim` | planilha hidrológica completa |
| `GET /api/postos` | ESALQ + postos do INMET em SP |
| `GET /api/balanco?fonte&codigo&inicio&fim&cad&escala` | balanço hídrico (`fonte`: `esalq`, `inmet` ou `nasa`) |

## Estrutura

```
api/index.py            rotas da API
hidro/                  leitura dos arquivos, agregações, eventos, balanço, exportação
scripts/                atualização dos dados e migração dos CSVs antigos
dados/                  séries guardadas (atualizadas pelo GitHub Actions)
src/                    site em React
tests/                  testes dos cálculos e da API
.github/workflows/      atualização semanal dos dados
```

## Próximos passos

- Novos cálculos hidrológicos entram em `hidro/` (um módulo por cálculo), com uma rota em `api/index.py` e uma página ou seção em `src/paginas/`.

## Fontes dos dados

- Estação automática da ESALQ/USP (LEB): https://www.esalq.usp.br/departamentos/leb/automatica/pagina6.html (o endereço antigo, www.leb.esalq.usp.br, saiu do ar; o sistema tenta os dois)
- INMET, dados históricos das estações automáticas: https://portal.inmet.gov.br/dadoshistoricos
- NASA POWER (estimativas por satélite, usadas só quando escolhidas): https://power.larc.nasa.gov/
- Contorno do estado de SP: IBGE, via [GeoDadosBrasil](https://github.com/cristoferluch/GeoDadosBrasil)
