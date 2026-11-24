import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { obter } from './api.js';

const ContextoMeta = createContext({});

const CHAVE_ULTIMO = 'ultimo-posto';

/** Último posto aberto (para o link "Painel do posto" do topo). */
export function ultimoPosto() {
  try {
    return window.localStorage.getItem(CHAVE_ULTIMO) || 'esalq';
  } catch {
    return 'esalq';
  }
}

function lembrarPosto(id) {
  try {
    window.localStorage.setItem(CHAVE_ULTIMO, id);
  } catch {
    /* navegador sem armazenamento local */
  }
}

/**
 * Informações do posto aberto (ESALQ ou INMET): período com dados, anos,
 * origem do ano corrente. `api` é o prefixo das rotas do posto.
 */
export function ProvedorPosto({ id, children }) {
  const [estado, setEstado] = useState({ id, meta: null, erro: null });
  const [atualizando, setAtualizando] = useState(false);
  const [versao, setVersao] = useState(0);
  const api = `/api/posto/${encodeURIComponent(id)}`;

  useEffect(() => {
    let ativo = true;
    setEstado({ id, meta: null, erro: null });
    obter(`${api}/meta`)
      .then((meta) => {
        if (!ativo) return;
        setEstado({ id, meta, erro: null });
        lembrarPosto(meta.posto.id);
      })
      .catch((erro) => ativo && setEstado({ id, meta: null, erro }));
    return () => {
      ativo = false;
    };
  }, [id, api]);

  const atualizar = useCallback(async () => {
    setAtualizando(true);
    try {
      const novo = await obter(`${api}/meta`, { atualizar: true, t: Date.now() });
      setEstado({ id, meta: novo, erro: null });
      setVersao((v) => v + 1);
    } catch (erro) {
      setEstado((e) => ({ ...e, erro }));
    } finally {
      setAtualizando(false);
    }
  }, [api, id]);

  // Enquanto o meta do novo posto não chega, não expõe o do posto anterior
  const meta = estado.id === id ? estado.meta : null;
  const erro = estado.id === id ? estado.erro : null;
  const valor = useMemo(
    () => ({ id, api, meta, posto: meta?.posto ?? null, erro, atualizando, atualizar, versao }),
    [id, api, meta, erro, atualizando, atualizar, versao],
  );
  return <ContextoMeta.Provider value={valor}>{children}</ContextoMeta.Provider>;
}

export function useMeta() {
  return useContext(ContextoMeta);
}

/** Textos que mudam com a resolução do posto (15 min na ESALQ, 1 h no INMET). */
export function textosResolucao(minutos) {
  if (minutos === 60) {
    return {
      registro: 'registro horário',
      registros: 'registros horários',
      intervalo: '1 hora',
      noIntervalo: 'em 1 h',
      tituloDados: 'Dados horários',
      maiorIntensidade: 'Maior intensidade (1 h)',
    };
  }
  return {
    registro: 'registro de 15 min',
    registros: 'registros de 15 min',
    intervalo: '15 minutos',
    noIntervalo: 'em 15 min',
    tituloDados: 'Dados de 15 minutos',
    maiorIntensidade: 'Maior intensidade (15 min)',
  };
}
