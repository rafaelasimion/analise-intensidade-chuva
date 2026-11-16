// Rótulos, unidades e formatação das colunas vindas da API.

export const COLUNAS = {
  data_hora: { rotulo: 'Data e hora', tipo: 'datahora' },
  periodo: { rotulo: 'Período', tipo: 'texto' },
  inicio: { rotulo: 'Início', tipo: 'datahora' },
  fim: { rotulo: 'Fim', tipo: 'datahora' },
  chuva_mm: { rotulo: 'Chuva (mm)', tipo: 'num', casas: 1 },
  intensidade_mm_h: { rotulo: 'Intensidade (mm/h)', tipo: 'num', casas: 1 },
  intensidade_max_mm_h: { rotulo: 'Intensidade máx. (mm/h)', tipo: 'num', casas: 1 },
  momento_intensidade_max: { rotulo: 'Quando', tipo: 'datahora' },
  chuva_acum_dia_mm: { rotulo: 'Acumulada no dia (mm)', tipo: 'num', casas: 1 },
  dias_chuva: { rotulo: 'Dias com chuva', tipo: 'num', casas: 0 },
  chuva_max_diaria_mm: { rotulo: 'Maior chuva diária (mm)', tipo: 'num', casas: 1 },
  data_chuva_max_diaria: { rotulo: 'Dia da maior chuva', tipo: 'data' },
  temp_c: { rotulo: 'Temp. média (°C)', tipo: 'num', casas: 1 },
  temp_max_c: { rotulo: 'Temp. máx. (°C)', tipo: 'num', casas: 1 },
  temp_min_c: { rotulo: 'Temp. mín. (°C)', tipo: 'num', casas: 1 },
  temp_max_media_c: { rotulo: 'Média das máx. (°C)', tipo: 'num', casas: 1 },
  temp_min_media_c: { rotulo: 'Média das mín. (°C)', tipo: 'num', casas: 1 },
  ur_pct: { rotulo: 'Umidade (%)', tipo: 'num', casas: 0 },
  vento_ms: { rotulo: 'Vento (m/s)', tipo: 'num', casas: 1 },
  vento_max_ms: { rotulo: 'Rajada (m/s)', tipo: 'num', casas: 1 },
  vento_dir_graus: { rotulo: 'Direção (°)', tipo: 'num', casas: 0 },
  rad_w_m2: { rotulo: 'Radiação (W/m²)', tipo: 'num', casas: 0 },
  rad_mj_m2: { rotulo: 'Radiação (MJ/m²·dia)', tipo: 'num', casas: 1 },
  pressao_hpa: { rotulo: 'Pressão (hPa)', tipo: 'num', casas: 1 },
  dias_com_dados: { rotulo: 'Dias com dados', tipo: 'num', casas: 0 },
  cobertura_pct: { rotulo: 'Dados (%)', tipo: 'num', casas: 0 },
};

export function colunasDe(chaves, sobrescrever = {}) {
  return chaves
    .filter((c) => COLUNAS[c] || sobrescrever[c])
    .map((c) => ({ chave: c, ...COLUNAS[c], ...sobrescrever[c] }));
}

/** Linhas de tabela a partir da série colunar ({t: [...], campo: [...]}). */
export function linhasDaSerie(serie, campos) {
  if (!serie?.t) return [];
  return serie.t.map((t, i) => {
    const linha = { id: t, t };
    for (const c of campos) linha[c] = serie[c]?.[i] ?? null;
    return linha;
  });
}
