export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method, headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const result = await response.json().catch(() => { throw new Error('A API local está indisponível. Verifique se ela está em execução.') })
  if (!response.ok) throw new Error(result.detail || 'Não foi possível concluir a operação.')
  return result
}
