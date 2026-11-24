import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import Dashboard from './Dashboard'
import { api } from './api'

type Configuration = {
  board_id: number; task_type_ids: string[]; subtask_type_ids: string[]; bug_type_ids: string[]
  work_column_ids: string[]; task_final_status_ids: string[]; bug_final_status_ids: string[]
  sprint_ids: string[]; ai_adoption_date: string | null
}
type Project = {
  id: string; name: string; jira_url: string; project_key: string; config_version: number
  configured: boolean; configuration: Configuration | null; results_state: string
  connection: { credentials_saved: boolean; status: string | null; tested_at: string | null }
}
type Option = { id: string; name: string }
type Metadata = {
  boards: { id: number; name: string; type: string }[]; board_id: number | null
  issue_types: (Option & { subtask: boolean; statuses: Option[] })[]
  columns: (Option & { status_ids: string[] })[]
  sprints: { id: number; name: string; state: string }[]; fetched_at: string
}
const emptyConnection = () => ({ name: '', jira_url: '', project_key: '', email: '', token: '' })
const emptyConfiguration = (): Configuration => ({
  board_id: 0, task_type_ids: [], subtask_type_ids: [], bug_type_ids: [], work_column_ids: [],
  task_final_status_ids: [], bug_final_status_ids: [], sprint_ids: [], ai_adoption_date: null,
})
function Choices({ title, options, value, onChange }: {
  title: string; options: Option[]; value: string[]; onChange: (ids: string[]) => void
}) {
  return <fieldset className="choices"><legend>{title}</legend>
    {options.length === 0 && <span className="muted">Nenhuma opção disponível.</span>}
    {options.map(option => <label className="check" key={option.id}>
      <input type="checkbox" checked={value.includes(option.id)} onChange={event => onChange(
        event.target.checked ? [...value, option.id] : value.filter(id => id !== option.id),
      )} /><span>{option.name}</span><small>{option.id}</small>
    </label>)}
  </fieldset>
}

function App() {
  const [view, setView] = useState<'dashboard' | 'configuration'>('configuration')
  const [projects, setProjects] = useState<Project[]>([])
  const [selected, setSelected] = useState<Project | null>(null)
  const [connection, setConnection] = useState(emptyConnection)
  const [metadata, setMetadata] = useState<Metadata | null>(null)
  const [rules, setRules] = useState<Configuration>(emptyConfiguration)
  const [board, setBoard] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { api<Project[]>('/projects').then(setProjects).catch(e => setError(e.message)) }, [])

  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : 'Falha de comunicação com a API local.') }
    finally { setBusy(false) }
  }
  function accept(project: Project) {
    setSelected(project)
    setProjects(previous => [...previous.filter(item => item.id !== project.id), project])
    setConnection({ name: project.name, jira_url: project.jira_url, project_key: project.project_key, email: '', token: '' })
    setRules(project.configuration ? Object.fromEntries(Object.keys(emptyConfiguration()).map(key => [key, project.configuration![key as keyof Configuration]])) as unknown as Configuration : emptyConfiguration())
    setBoard(project.configuration ? String(project.configuration.board_id) : '')
  }
  async function choose(project: Project) {
    await perform(async () => {
      const [fresh, cached] = await Promise.all([
        api<Project>(`/projects/${project.id}`), api<Metadata | null>(`/projects/${project.id}/metadata`),
      ])
      accept(fresh); setMetadata(cached); setView(fresh.configured ? 'dashboard' : 'configuration')
      if (!fresh.configuration && cached?.board_id) setBoard(String(cached.board_id))
    })
  }
  function createNew() {
    setView('configuration'); setSelected(null); setConnection(emptyConnection()); setMetadata(null)
    setRules(emptyConfiguration()); setBoard(''); setError(''); setNotice('')
  }
  async function saveConnection(event: FormEvent) {
    event.preventDefault()
    await perform(async () => {
      const body = { ...connection, email: connection.email || null, token: connection.token || null }
      const result = await api<Project>(selected ? `/projects/${selected.id}` : '/projects', selected ? 'PUT' : 'POST', body)
      accept(result)
      setNotice('Conexão salva. Busque as opções do Jira para configurar o projeto.')
    })
  }
  async function refresh(boardId: number | null) {
    if (!selected) return
    await perform(async () => {
      const result = await api<Metadata>(`/projects/${selected.id}/metadata`, 'POST', { board_id: boardId })
      setMetadata(result); setBoard(result.board_id ? String(result.board_id) : '')
      setNotice(boardId ? 'Opções do quadro atualizadas. Revise as seleções e salve a configuração.' : 'Opções carregadas. Escolha um quadro Scrum.')
    })
  }
  async function saveRules(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    await perform(async () => {
      const result = await api<Project>(`/projects/${selected.id}/configuration`, 'PUT', { ...rules, board_id: Number(board) })
      accept(result)
      setNotice(`Configuração salva · versão ${result.config_version}.`)
    })
  }
  const setIds = (key: keyof Configuration) => (ids: string[]) => setRules(previous => ({ ...previous, [key]: ids }))
  const typeOptions = metadata?.issue_types || []
  const finalOptions = (ids: string[]) => Array.from(new Map(typeOptions.filter(item => ids.includes(item.id))
    .flatMap(item => item.statuses).map(item => [item.id, item])).values())
  const boardReady = !!metadata?.board_id && metadata.board_id === Number(board)

  return <div className="shell">
    <aside>
      <div className="brand"><img src="/logo-inverted.svg" alt="" width="34" height="34" />echiro</div>
      <div className="nav-heading">SEUS PROJETOS <span>{projects.length}</span></div>
      <nav aria-label="Projetos">{projects.map(project => <button key={project.id} disabled={busy}
        className={`project-link ${selected?.id === project.id ? 'active' : ''}`} onClick={() => choose(project)}>
        <span className="project-icon">{project.project_key.slice(0, 2)}</span>
        <span><strong>{project.name}</strong><small>{project.configured ? 'Configurado' : 'Configuração pendente'}</small></span>
      </button>)}</nav>
      <button className="new-project" onClick={createNew} disabled={busy}>+ Novo projeto</button>
      <div className="local-note"><span className="dot" /> Ambiente local<br /><small>Jira Cloud · somente leitura</small></div>
    </aside>
    <main>
      <header><div><div className="eyebrow">HUB DE PROJETOS / {view === 'dashboard' ? 'ANÁLISE' : 'CONFIGURAÇÃO'}</div>
        <h1>{selected ? selected.name : 'Adicionar projeto'}</h1>
        <p>{view === 'dashboard' ? 'Acompanhe o trabalho, as entregas e os bugs por sprint.' : 'Prepare a conexão e escolha as regras para acompanhar o projeto.'}</p></div>
        {selected && <span className={`badge ${selected.configured ? 'success' : ''}`}>{selected.configured ? `Configurado · v${selected.config_version}` : 'Configuração pendente'}</span>}
      </header>
      {error && <div className="alert error" role="alert">{error}</div>}
      {notice && <div className="alert notice" role="status">{notice}</div>}
      {busy && <div className="progress" role="status">Processando… As consultas ao Jira podem levar alguns segundos.</div>}
      {selected && <div className="view-tabs" role="tablist" aria-label="Área do projeto"><button role="tab" aria-selected={view === 'dashboard'} onClick={() => setView('dashboard')} disabled={busy || !selected.configured}>Dashboard</button><button role="tab" aria-selected={view === 'configuration'} onClick={() => setView('configuration')} disabled={busy}>Configuração</button></div>}
      {selected && view === 'dashboard' ? <Dashboard key={selected.id} projectId={selected.id} onConfigure={() => setView('configuration')} /> : <>
      <section className="panel">
        <div className="section-title"><span className="step">1</span><div><h2>Conexão com o Jira</h2><p>Credenciais independentes para cada projeto.</p></div></div>
        <form onSubmit={saveConnection}><fieldset disabled={busy} className="form-fields">
          <div className="grid">
            <label>Nome do projeto<input required maxLength={120} value={connection.name} onChange={e => setConnection({ ...connection, name: e.target.value })} placeholder="Nome para identificar o projeto" /></label>
            <label>Chave no Jira<input required maxLength={60} readOnly={!!selected} value={connection.project_key} onChange={e => setConnection({ ...connection, project_key: e.target.value.toUpperCase() })} placeholder="PROJ" /></label>
            <label className="wide">URL do Jira Cloud<input required type="url" readOnly={!!selected} value={connection.jira_url} onChange={e => setConnection({ ...connection, jira_url: e.target.value })} placeholder="https://empresa.atlassian.net" /></label>
            <label>E-mail Atlassian<input type="email" required={!selected} autoComplete="off" value={connection.email} onChange={e => setConnection({ ...connection, email: e.target.value })} placeholder={selected ? 'Deixe vazio para manter o e-mail salvo' : 'voce@empresa.com'} /></label>
            <label>Token de API<input type="password" required={!selected} autoComplete="new-password" value={connection.token} onChange={e => setConnection({ ...connection, token: e.target.value })} placeholder={selected ? 'Deixe vazio para manter o token salvo' : 'Token da sua conta Atlassian'} /></label>
          </div>
          <p className="hint">{selected ? 'Para trocar o site ou a chave, cadastre outro projeto. ' : ''}E-mail e token ficam protegidos nesta máquina e não são exibidos após salvar.</p>
          <div className="actions"><button className="primary" type="submit">{selected ? 'Salvar conexão' : 'Cadastrar projeto'}</button>
            {selected && <button type="button" onClick={() => perform(async () => {
              const result = await api<{ message: string }>(`/projects/${selected.id}/test-connection`, 'POST')
              setNotice(result.message)
              const fresh = await api<Project>(`/projects/${selected.id}`)
              setSelected(fresh); setProjects(previous => previous.map(item => item.id === fresh.id ? fresh : item))
            })}>Testar conexão salva</button>}
          </div>
          {selected?.connection.tested_at && <p className="hint">Último teste bem-sucedido: {new Date(selected.connection.tested_at).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })}</p>}
        </fieldset></form>
      </section>
      <section className={`panel ${!selected ? 'waiting' : ''}`}>
        <div className="section-title"><span className="step">2</span><div><h2>Regras do projeto</h2><p>As opções são lidas do Jira quando você solicitar.</p></div></div>
        {!selected ? <p className="empty">Cadastre a conexão para buscar quadros, tipos e sprints.</p> : <>
          <div className="actions"><button disabled={busy} onClick={() => refresh(board ? Number(board) : null)}>{metadata ? 'Atualizar opções do Jira' : 'Buscar opções do Jira'}</button>
            {metadata && <small className="muted">Obtidas em {new Date(metadata.fetched_at).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })}</small>}
          </div>
          {metadata && <form onSubmit={saveRules}><fieldset disabled={busy} className="form-fields">
            <div className="board-row"><div className="board-field"><label htmlFor="board">Quadro Scrum</label><select id="board" value={board} onChange={e => { setBoard(e.target.value); setRules(emptyConfiguration()) }} required>
              <option value="">Selecione um quadro</option>{metadata.boards.filter(item => item.type === 'scrum').map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select></div><button type="button" disabled={!board || busy} onClick={() => refresh(Number(board))}>Carregar quadro</button></div>
            {boardReady && <>
              <div className="grid selections">
                <Choices title="Tipos de tarefa" options={typeOptions.filter(item => !item.subtask)} value={rules.task_type_ids} onChange={setIds('task_type_ids')} />
                <Choices title="Tipos de subtarefa" options={typeOptions.filter(item => item.subtask)} value={rules.subtask_type_ids} onChange={setIds('subtask_type_ids')} />
                <Choices title="Tipos de bug" options={typeOptions.filter(item => !item.subtask)} value={rules.bug_type_ids} onChange={setIds('bug_type_ids')} />
                <Choices title="Colunas de trabalho" options={metadata.columns} value={rules.work_column_ids} onChange={setIds('work_column_ids')} />
                <Choices title="Status finais de tarefas e subtarefas" options={finalOptions([...rules.task_type_ids, ...rules.subtask_type_ids])} value={rules.task_final_status_ids} onChange={setIds('task_final_status_ids')} />
                <Choices title="Status finais de bugs" options={finalOptions(rules.bug_type_ids)} value={rules.bug_final_status_ids} onChange={setIds('bug_final_status_ids')} />
              </div>
              <div className="sprint-heading"><h3>Sprints para análise</h3><button type="button" onClick={() => setIds('sprint_ids')(metadata.sprints.map(item => String(item.id)))}>Selecionar todas</button><button type="button" onClick={() => setIds('sprint_ids')([])}>Limpar</button></div>
              <Choices title="Selecione uma ou mais sprints" options={metadata.sprints.map(item => ({ id: String(item.id), name: `${item.name} · ${{ closed: 'encerrada', active: 'em andamento', future: 'futura' }[item.state] || item.state}` }))} value={rules.sprint_ids} onChange={setIds('sprint_ids')} />
              <label className="date-field">Data de adoção de IA<input type="date" value={rules.ai_adoption_date || ''} onChange={e => setRules({ ...rules, ai_adoption_date: e.target.value || null })} /><small>Opcional. Preencha quando o marco de adoção estiver definido.</small></label>
              <p className="hint">Cada tarefa e subtarefa valerá uma unidade. Selecione os tipos correspondentes; histórias e épicos ficam fora das contagens. Alterar as regras exige recalcular os indicadores.</p>
              {selected.results_state === 'recalculation_required' && <div className="alert notice">Há resultados de uma configuração anterior aguardando recálculo.</div>}
              <div className="actions"><button className="primary" type="submit">Salvar configuração</button><small className="muted">{selected.config_version ? `Versão atual: ${selected.config_version}` : 'Ainda não configurado'}</small></div>
            </>}
          </fieldset></form>}
        </>}
      </section>
      <footer>O cadastro não inicia a sincronização. Abra o dashboard e solicite a coleta quando quiser atualizar o histórico.</footer>
      </> }
    </main>
  </div>
}

export default App
