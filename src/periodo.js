import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { isoData, paraData } from './formato.js';
import { useMeta } from './meta.jsx';

/** Dia do último registro (o registro de 00:00 pertence ao dia anterior). */
export function diaDoRegistro(iso) {
  const d = paraData(iso);
  if (!d) return null;
  return new Date(d.getTime() - 1000);
}

function somarDias(data, dias) {
  const d = new Date(data.getFullYear(), data.getMonth(), data.getDate());
  d.setDate(d.getDate() + dias);
  return d;
}

export function listaPresets(limites) {
  const fim = diaDoRegistro(limites?.fim) ?? new Date();
  const ano = fim.getFullYear();
  return [
    { id: '7d', rotulo: '7 dias' },
    { id: '30d', rotulo: '30 dias' },
    { id: '12m', rotulo: '12 meses' },
    { id: 'ano', rotulo: String(ano) },
    { id: 'anoant', rotulo: String(ano - 1) },
    { id: 'tudo', rotulo: 'Toda a série' },
  ];
}

export function calcularPreset(id, limites) {
  const fim = diaDoRegistro(limites?.fim) ?? new Date();
  const primeiro = paraData(limites?.inicio) ?? new Date(fim.getFullYear(), 0, 1);
  const ano = fim.getFullYear();
  switch (id) {
    case '7d':
      return { inicio: isoData(somarDias(fim, -6)), fim: isoData(fim) };
    case '12m':
      return { inicio: isoData(somarDias(fim, -364)), fim: isoData(fim) };
    case 'ano':
      return { inicio: `${ano}-01-01`, fim: isoData(fim) };
    case 'anoant':
      return { inicio: `${ano - 1}-01-01`, fim: `${ano - 1}-12-31` };
    case 'tudo':
      return { inicio: isoData(primeiro), fim: isoData(fim) };
    case '30d':
    default:
      return { inicio: isoData(somarDias(fim, -29)), fim: isoData(fim) };
  }
}

/**
 * Período guardado na URL (?p=30d ou ?inicio=…&fim=…), compartilhado entre
 * Painel, Dados, Eventos e Relatórios.
 */
export function usePeriodo(padrao = '30d') {
  const [params, setParams] = useSearchParams();
  const { meta } = useMeta();
  const limites = meta?.limites;
  const pIni = params.get('inicio');
  const pFim = params.get('fim');
  const pPreset = params.get('p');

  const periodo = useMemo(() => {
    if (pIni && pFim) return { inicio: pIni, fim: pFim, preset: null };
    if (!limites) return null;
    const id = pPreset ?? padrao;
    return { ...calcularPreset(id, limites), preset: id };
  }, [pIni, pFim, pPreset, padrao, limites]);

  const escolherPreset = useCallback((id) => {
    setParams((atual) => {
      const novo = new URLSearchParams(atual);
      novo.delete('inicio');
      novo.delete('fim');
      novo.set('p', id);
      return novo;
    });
  }, [setParams]);

  const escolherIntervalo = useCallback((inicio, fim) => {
    setParams((atual) => {
      const novo = new URLSearchParams(atual);
      novo.delete('p');
      novo.set('inicio', inicio);
      novo.set('fim', fim);
      return novo;
    });
  }, [setParams]);

  return { periodo, escolherPreset, escolherIntervalo, presets: listaPresets(limites) };
}

/** Parte da URL que leva o período para outra página. */
export function buscaDoPeriodo(search) {
  const atual = new URLSearchParams(search);
  const novo = new URLSearchParams();
  for (const chave of ['p', 'inicio', 'fim']) {
    if (atual.get(chave)) novo.set(chave, atual.get(chave));
  }
  const s = novo.toString();
  return s ? `?${s}` : '';
}
