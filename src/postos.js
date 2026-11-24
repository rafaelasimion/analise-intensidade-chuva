import { useEffect, useState } from 'react';
import { obter } from './api.js';

// A lista de postos é a mesma em todas as páginas: busca uma vez só.
let cache = null;

export function usePostos() {
  const [estado, setEstado] = useState(() => ({ dados: cache?.dados ?? null, erro: null }));
  useEffect(() => {
    let ativo = true;
    if (!cache) {
      const promessa = obter('/api/postos').then((d) => {
        cache.dados = d;
        return d;
      });
      cache = { promessa, dados: null };
      promessa.catch(() => {
        cache = null;
      });
    }
    cache.promessa
      .then((dados) => ativo && setEstado({ dados, erro: null }))
      .catch((erro) => ativo && setEstado({ dados: null, erro }));
    return () => {
      ativo = false;
    };
  }, []);
  return estado;
}

/** Nome para mostrar: "ESALQ/USP – Piracicaba", "São Carlos"… */
export function nomePosto(p) {
  if (!p) return '';
  return p.fonte === 'esalq' ? 'ESALQ/USP – Piracicaba' : p.nome;
}

/** Nome curto para gráficos e tabelas apertadas. */
export function nomeCurto(p) {
  if (!p) return '';
  return p.fonte === 'esalq' ? 'ESALQ/USP' : p.nome;
}

/** "Estação automática do INMET (A711), registros horários" */
export function descricaoPosto(p) {
  if (!p) return '';
  if (p.fonte === 'esalq') return 'Estação automática do LEB/ESALQ/USP, registros a cada 15 minutos';
  return `Estação automática do INMET (${p.codigo}), registros horários`;
}

/** Distância em km entre dois pontos {lat, lon}. */
export function distanciaKm(a, b) {
  const R = 6371;
  const rad = (g) => (g * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Lista para <select>, ESALQ primeiro e os demais em ordem alfabética. */
export function ordenarParaLista(postos) {
  return [...(postos ?? [])].sort((a, b) =>
    a.fonte === 'esalq' ? -1 : b.fonte === 'esalq' ? 1 : a.nome.localeCompare(b.nome, 'pt-BR'),
  );
}
