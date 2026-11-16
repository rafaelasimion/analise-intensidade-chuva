// Formatação em português do Brasil.

const formatadores = new Map();

function formatador(casas) {
  if (!formatadores.has(casas)) {
    formatadores.set(
      casas,
      new Intl.NumberFormat('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }),
    );
  }
  return formatadores.get(casas);
}

export function num(valor, casas = 1) {
  if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return '–';
  return formatador(casas).format(Number(valor));
}

/** Converte "AAAA-MM-DD" (sem fuso) ou "AAAA-MM-DDTHH:MM:SS" em Date local. */
export function paraData(iso) {
  if (!iso) return null;
  if (iso instanceof Date) return iso;
  const s = String(iso);
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (!m) return new Date(s);
  const [, a, me, d, h = '0', mi = '0', se = '0'] = m;
  return new Date(Number(a), Number(me) - 1, Number(d), Number(h), Number(mi), Number(se));
}

const doisDigitos = (n) => String(n).padStart(2, '0');

export function isoData(data) {
  return `${data.getFullYear()}-${doisDigitos(data.getMonth() + 1)}-${doisDigitos(data.getDate())}`;
}

export function isoMes(data) {
  return `${data.getFullYear()}-${doisDigitos(data.getMonth() + 1)}`;
}

export function dataBR(iso) {
  const d = paraData(iso);
  if (!d || Number.isNaN(d.getTime())) return '–';
  return `${doisDigitos(d.getDate())}/${doisDigitos(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export function dataHoraBR(iso) {
  const d = paraData(iso);
  if (!d || Number.isNaN(d.getTime())) return '–';
  return `${dataBR(d)} ${doisDigitos(d.getHours())}:${doisDigitos(d.getMinutes())}`;
}

export const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto',
  'setembro', 'outubro', 'novembro', 'dezembro'];
export const MESES_CURTOS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

export function mesAno(iso) {
  const d = paraData(iso);
  return d ? `${MESES_CURTOS[d.getMonth()]}/${d.getFullYear()}` : '–';
}

function diaExtenso(d) {
  return d.getDate() === 1 ? '1º' : String(d.getDate());
}

/** "3 a 31 de março de 2026", "28 de fevereiro a 3 de março de 2026"… */
export function periodoExtenso(inicioIso, fimIso) {
  const a = paraData(inicioIso);
  const b = paraData(fimIso);
  if (!a || !b) return '';
  if (isoData(a) === isoData(b)) return `${diaExtenso(a)} de ${MESES[a.getMonth()]} de ${a.getFullYear()}`;
  if (a.getFullYear() === b.getFullYear()) {
    if (a.getMonth() === b.getMonth()) {
      return `${diaExtenso(a)} a ${diaExtenso(b)} de ${MESES[b.getMonth()]} de ${b.getFullYear()}`;
    }
    return `${diaExtenso(a)} de ${MESES[a.getMonth()]} a ${diaExtenso(b)} de ${MESES[b.getMonth()]} de ${b.getFullYear()}`;
  }
  return `${diaExtenso(a)} de ${MESES[a.getMonth()]} de ${a.getFullYear()} a ${diaExtenso(b)} de ${MESES[b.getMonth()]} de ${b.getFullYear()}`;
}

export function duracao(minutos) {
  if (minutos === null || minutos === undefined) return '–';
  if (minutos < 60) return `${Math.round(minutos)} min`;
  const h = Math.floor(minutos / 60);
  const m = Math.round(minutos % 60);
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function escaparHtml(texto) {
  return String(texto ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}
