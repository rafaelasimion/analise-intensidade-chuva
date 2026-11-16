import { useCallback, useEffect, useRef, useState } from 'react';

// Em produção a API está no mesmo domínio (/api). VITE_API_URL permite apontar para outro servidor.
export const BASE_API = import.meta.env.VITE_API_URL ?? '';

export function urlApi(caminho, params = {}) {
  const url = new URL(BASE_API + caminho, window.location.origin);
  for (const [chave, valor] of Object.entries(params)) {
    if (valor !== undefined && valor !== null && valor !== '' && valor !== false) {
      url.searchParams.set(chave, String(valor));
    }
  }
  return url.toString();
}

function mensagemDeErro(corpo, status) {
  const detalhe = corpo?.detail;
  if (typeof detalhe === 'string') return detalhe;
  if (Array.isArray(detalhe)) return detalhe.map((d) => d.msg).join('; ');
  return `O servidor respondeu com erro ${status}.`;
}

export async function obter(caminho, params, sinal) {
  let resposta;
  try {
    resposta = await fetch(urlApi(caminho, params), { signal: sinal });
  } catch (erro) {
    if (erro.name === 'AbortError') throw erro;
    throw new Error('Sem conexão com o servidor. Verifique a internet e tente de novo.');
  }
  if (!resposta.ok) {
    let corpo = null;
    try {
      corpo = await resposta.json();
    } catch {
      /* resposta sem JSON */
    }
    throw new Error(mensagemDeErro(corpo, resposta.status));
  }
  return resposta.json();
}

/**
 * Busca dados da API. Enquanto recarrega, mantém os dados anteriores
 * (a tela não pisca); `carregando` indica a troca.
 */
export function useApi(caminho, params, ativo = true) {
  const [estado, setEstado] = useState({ dados: null, erro: null, carregando: ativo });
  const chave = JSON.stringify(params ?? {});
  const [versao, setVersao] = useState(0);
  const ultimo = useRef(0);

  useEffect(() => {
    if (!ativo || !caminho) return undefined;
    const id = ++ultimo.current;
    const controle = new AbortController();
    setEstado((e) => ({ ...e, carregando: true, erro: null }));
    obter(caminho, JSON.parse(chave), controle.signal)
      .then((dados) => {
        if (id === ultimo.current) setEstado({ dados, erro: null, carregando: false });
      })
      .catch((erro) => {
        if (erro.name === 'AbortError') return;
        if (id === ultimo.current) setEstado((e) => ({ ...e, erro, carregando: false }));
      });
    return () => controle.abort();
  }, [caminho, chave, ativo, versao]);

  const recarregar = useCallback(() => setVersao((v) => v + 1), []);
  return { ...estado, recarregar };
}
