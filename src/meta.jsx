import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { obter } from './api.js';

const ContextoMeta = createContext(null);

/** Informações gerais da estação (anos, primeiro/último registro, origem do ano corrente). */
export function ProvedorMeta({ children }) {
  const [meta, setMeta] = useState(null);
  const [erro, setErro] = useState(null);
  const [atualizando, setAtualizando] = useState(false);
  const [versao, setVersao] = useState(0);

  useEffect(() => {
    obter('/api/esalq/meta').then(setMeta).catch(setErro);
  }, []);

  const atualizar = useCallback(async () => {
    setAtualizando(true);
    try {
      const novo = await obter('/api/esalq/meta', { atualizar: true, t: Date.now() });
      setMeta(novo);
      setErro(null);
      setVersao((v) => v + 1);
    } catch (e) {
      setErro(e);
    } finally {
      setAtualizando(false);
    }
  }, []);

  const valor = useMemo(() => ({ meta, erro, atualizando, atualizar, versao }), [meta, erro, atualizando, atualizar, versao]);
  return <ContextoMeta.Provider value={valor}>{children}</ContextoMeta.Provider>;
}

export function useMeta() {
  return useContext(ContextoMeta);
}
