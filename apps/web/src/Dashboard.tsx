import { useEffect, useId, useState } from 'react'
import { api } from './api'

type MetricName = 'worked' | 'completed' | 'reopened' | 'bugs_total' | 'bugs_new' | 'bugs_existing'
type Ticket = { id: string; key: string; kind: string; url: string; events?: { at: string; history_id: string; from: string; to: string; from_name?: string | null; to_name?: string | null }[] }
type Metric = { value: number | null; known_count: number; tickets: Ticket[]; limitations: { ticket?: string; reason: string }[] }
type Sprint = {
  id: string; name: string; ai_period: string; reopening_events: number
  window: { state: string; availability: string; partial: boolean; start_utc: string | null; end_utc: string | null; reason: string | null }
  metrics: Record<MetricName, Metric>; ratio: { value: number | null; status: string }
}
type Run = { id: string; status: string; started_at: string; finished_at: string | null; error_code: string | null
  checkpoint: { stage: string; read?: number; total?: number; reused?: number; retry_in_seconds?: number } }
type Sync = { latest: Run | null; last_success: { collected_at: string } | null }
type Data = {
  state: string; sprints: Sprint[]; sync: Sync; collected_at?: string; computed_at?: string; config_version?: number
  ai_adoption_date?: string | null; limitations?: string[]; project: { configuration: { ai_adoption_date: string | null } | null }
}
const labels: Record<MetricName, string> = {
  worked: 'Tarefas e subtarefas trabalhadas', completed: 'Primeiras entregas', reopened: 'Tickets reabertos',
  bugs_total: 'Bugs totais', bugs_new: 'Bugs novos', bugs_existing: 'Bugs existentes',
}
const periodLabels: Record<string, string> = { before: 'Antes da IA', after: 'Após a IA', transition: 'Transição', not_configured: 'Sem marco de IA', unavailable: 'Indisponível' }
const stageLabels: Record<string, string> = { completed: 'Base atualizada', starting: 'Preparando', metadata: 'Lendo opções do projeto', search: 'Buscando tickets', histories: 'Lendo históricos', publishing: 'Salvando a base', waiting_retry: 'Aguardando limite do Jira' }
const statusLabels: Record<string, string> = { running: 'Sincronizando', succeeded: 'Concluída', failed: 'Falhou', interrupted: 'Interrompida' }
const date = (value?: string | null) => value ? new Date(value).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' }) : 'Ainda não disponível'
const number = (value: number | null | undefined, digits = 0) => value == null ? 'Indisponível' : value.toLocaleString('pt-BR', { maximumFractionDigits: digits })

function Evolution({ rows, adoption }: { rows: Sprint[]; adoption: string | null }) {
  const [mode, setMode] = useState<'volume' | 'ratio'>('volume')
  const [hovered, setHovered] = useState<string | null>(null)
  const [focused, setFocused] = useState<string | null>(null)
  const tooltipId = useId()
  const available = rows.filter(row => row.window.availability === 'available')
  const series = mode === 'volume'
    ? [{ key: 'worked', label: 'Trabalhadas', color: '#d5f185' }, { key: 'completed', label: 'Entregas', color: '#91b9ff' }, { key: 'bugs_total', label: 'Bugs', color: '#f2ac88' }]
    : [{ key: 'ratio', label: 'Bugs ÷ trabalhadas', color: '#c3a4f2' }]
  const getValue = (row: Sprint, key: string) => key === 'ratio' ? row.ratio.value : row.metrics[key as MetricName].value
  const maximum = Math.max(1, ...available.flatMap(row => series.map(item => getValue(row, item.key) || 0)))
  const x = (index: number) => 52 + index * (680 / Math.max(1, available.length - 1))
  const y = (value: number) => 225 - value / maximum * 175
  const activeIndex = available.findIndex(row => row.id === (hovered || focused))
  const active = available[activeIndex]
  const ratioText = (row: Sprint) => row.ratio.status === 'not_calculable' ? 'Não calculável' : number(row.ratio.value, 2)
  const boundary = available.findIndex(row => row.ai_period === 'after' || row.ai_period === 'transition')
  return <section className="panel chart-panel"><div className="dashboard-section"><h2>Evolução por sprint</h2>
    <div className="segmented" aria-label="Indicador do gráfico"><button className={mode === 'volume' ? 'chosen' : ''} onClick={() => setMode('volume')}>Volumes</button><button className={mode === 'ratio' ? 'chosen' : ''} onClick={() => setMode('ratio')}>Proporção</button></div></div>
    {available.length === 0 ? <p className="empty">Selecione sprints com intervalos disponíveis para ver a evolução.</p> : <>
      <div className="chart-legend">{series.map(item => <span key={item.key}><i style={{ background: item.color }} />{item.label}</span>)}<span>○ Sprint em andamento</span></div>
      <div className="chart-interactive" onPointerLeave={() => setHovered(null)}>
      <svg className="evolution" viewBox="0 0 780 270" role="group" aria-label={mode === 'volume' ? 'Evolução de trabalhadas, primeiras entregas e bugs por sprint' : 'Evolução da proporção bugs por trabalhadas por sprint'}>
        {[0, 0.25, 0.5, 0.75, 1].map(factor => <g key={factor}><line x1="52" y1={y(maximum * factor)} x2="740" y2={y(maximum * factor)} stroke="#354259" /><text x="42" y={y(maximum * factor) + 4} textAnchor="end">{number(maximum * factor, 1)}</text></g>)}
        {boundary >= 0 && adoption && <g><line x1={x(boundary)} y1="30" x2={x(boundary)} y2="228" stroke="#c3a4f2" strokeDasharray="5 5" /><text x={Math.min(660, x(boundary) + 7)} y="22" fill="#c3a4f2">Marco de IA</text></g>}
        {active && <line x1={x(activeIndex)} y1="35" x2={x(activeIndex)} y2="230" stroke="#aabbd3" strokeDasharray="3 4" />}
        {series.map(item => <g key={item.key}>{available.map((row, index) => {
          const value = getValue(row, item.key), previous = index ? getValue(available[index - 1], item.key) : null
          return value === null ? null : <g key={row.id}>
            {previous !== null && <line x1={x(index - 1)} y1={y(previous)} x2={x(index)} y2={y(value)} stroke={item.color} strokeWidth="2" />}
            <circle cx={x(index)} cy={y(value)} r={active?.id === row.id ? 6 : 4} fill={row.window.partial ? '#192335' : item.color} stroke={item.color} strokeWidth="2"><title>{row.name}: {number(value, 2)}{row.window.partial ? ' (em andamento)' : ''}</title></circle>
          </g>
        })}</g>)}
        {available.map((row, index) => <text key={row.id} x={x(index)} y="248" textAnchor="middle">{index + 1}<title>{row.name}</title></text>)}
        {available.map((row, index) => {
          const left = index === 0 ? 42 : (x(index - 1) + x(index)) / 2
          const right = index === available.length - 1 ? 744 : (x(index) + x(index + 1)) / 2
          return <rect key={row.id} className="chart-hit-area" x={left} y="35" width={right - left} height="195" fill="transparent"
            tabIndex={0} role="button" aria-label={`${row.name}. Trabalhadas: ${number(row.metrics.worked.value)}. Entregas: ${number(row.metrics.completed.value)}. Bugs: ${number(row.metrics.bugs_total.value)}. Bugs por trabalhadas: ${ratioText(row)}.${row.window.partial ? ' Sprint em andamento, valores parciais.' : ''}`}
            aria-describedby={active?.id === row.id ? tooltipId : undefined}
            onPointerEnter={() => setHovered(row.id)} onFocus={() => { setHovered(null); setFocused(row.id) }} onBlur={() => setFocused(null)}
            onKeyDown={event => {
              if (event.key === 'Escape') { setHovered(null); setFocused(null) }
              if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setHovered(null); setFocused(row.id) }
              if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                event.preventDefault()
                const next = Math.max(0, Math.min(available.length - 1, index + (event.key === 'ArrowRight' ? 1 : -1)))
                event.currentTarget.ownerSVGElement?.querySelectorAll<SVGRectElement>('.chart-hit-area')[next]?.focus()
              }
            }} />
        })}
      </svg>
      {active && <div id={tooltipId} className="chart-tooltip" role="tooltip" style={{ left: `clamp(8px, calc(${x(activeIndex) / 780 * 100}% - 130px), calc(100% - 268px))` }}>
        <strong>{active.name}</strong>
        <small>{active.window.partial ? 'Em andamento · valores parciais' : 'Encerrada'} · {periodLabels[active.ai_period]}</small>
        <small>{date(active.window.start_utc)} → {date(active.window.end_utc)}</small>
        <dl>{(['worked', 'completed', 'bugs_total', 'bugs_new', 'bugs_existing'] as const).map(key => <div key={key}><dt>{key === 'worked' ? 'Trabalhadas' : labels[key]}</dt><dd>{number(active.metrics[key].value)}</dd></div>)}
          <div><dt>Bugs ÷ trabalhadas</dt><dd>{ratioText(active)}</dd></div>
        </dl>
      </div>}
      </div>
      <p className="hint">Passe o mouse sobre uma sprint para ver os valores. Pelo teclado, use Tab e as setas; Escape fecha os detalhes. A numeração segue a ordem das sprints na tabela. Pontos sem informação ficam sem ligação no gráfico. Sprints sobrepostas mantêm seus próprios intervalos.</p>
    </>}
  </section>
}

function Comparison({ rows, adoption, onConfigure }: { rows: Sprint[]; adoption: string | null; onConfigure: () => void }) {
  function group(name: string) {
    const all = rows.filter(row => row.ai_period === name)
    const included = all.filter(row => row.window.state === 'closed' && row.window.availability === 'available' && Object.values(row.metrics).every(metric => metric.value !== null))
    const total = (key: MetricName) => included.length ? included.reduce((sum, row) => sum + row.metrics[key].value!, 0) : null
    return { all, included, total, active: all.filter(row => row.window.partial).length }
  }
  return <section className="panel"><div className="dashboard-section"><h2>Adoção de IA</h2><button onClick={onConfigure}>{adoption ? 'Editar marco' : 'Definir data'}</button></div>
    {!adoption ? <p className="empty">Registre a data de adoção de IA na configuração para comparar os períodos. Os indicadores continuam disponíveis por sprint.</p> : <>
      <p className="hint">Marco: {adoption.split('-').reverse().join('/')} · início do dia em São Paulo. A comparação considera somente sprints encerradas e com dados completos da seleção atual.</p>
      <div className="comparison-grid">{(['before', 'after'] as const).map(name => {
        const values = group(name)
        return <div className="comparison" key={name}><h3>{periodLabels[name]}</h3><p>{values.included.length} sprints na comparação <small>de {values.all.length} selecionadas · {values.active} em andamento</small></p>
          {!values.included.length ? <p className="empty">Não há sprints encerradas com dados completos neste período.</p> : <dl>{(['worked', 'completed', 'bugs_total'] as const).map(key => <div key={key}><dt>{labels[key]}</dt><dd>{number(values.total(key))} <small>· média {number(values.total(key)! / values.included.length, 2)} por sprint</small></dd></div>)}<div><dt>Bugs ÷ trabalhadas</dt><dd>{values.total('worked') ? number(values.total('bugs_total')! / values.total('worked')!, 2) : 'Não calculável'}</dd></div></dl>}
        </div>
      })}</div>
      <p className="hint">{group('transition').all.length} sprints de transição ficam separadas e fora das médias. Sprints ativas ou incompletas também ficam fora da comparação. Os volumes somam as contagens de cada sprint; tickets podem participar de mais de uma sprint.</p>
    </>}
    <p className="hint">Os indicadores descrevem mudanças no período. Eles não demonstram causalidade da IA nem medem produtividade individual.</p>
  </section>
}

export default function Dashboard({ projectId, onConfigure }: { projectId: string; onConfigure: () => void }) {
  const [data, setData] = useState<Data | null>(null)
  const [sync, setSync] = useState<Sync | null>(null)
  const [selection, setSelection] = useState<string[] | null>(null)
  const [selectionMode, setSelectionMode] = useState<'include' | 'exclude'>('include')
  const [detail, setDetail] = useState<{ sprint: Sprint; key: MetricName } | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [ticketFilter, setTicketFilter] = useState('')

  useEffect(() => {
    let alive = true, observed = ''
    const load = () => api<Data>(`/projects/${projectId}/dashboard`).then(result => {
      if (alive) { setData(result); setSync(result.sync); observed = `${result.sync.latest?.id}:${result.sync.latest?.status}:${result.sync.latest?.finished_at}` }
    }).catch(e => { if (alive) setError(e.message) })
    void load()
    const interval = setInterval(() => {
      api<Sync>(`/projects/${projectId}/sync`).then(result => {
        if (!alive) return
        setSync(result)
        const running = result.latest?.status === 'running'
        const fingerprint = `${result.latest?.id}:${result.latest?.status}:${result.latest?.finished_at}`
        if (!running && fingerprint !== observed) { observed = fingerprint; void load() }
      }).catch(e => { if (alive) setError(e.message) })
    }, 2000)
    return () => { alive = false; clearInterval(interval) }
  }, [projectId])

  async function action(kind: 'sync' | 'sync/resume' | 'recalculate') {
    setBusy(true); setError(''); setDetail(null)
    try {
      if (kind === 'recalculate') {
        const result = await api<Data>(`/projects/${projectId}/recalculate`, 'POST')
        setData(result); setSync(result.sync)
      } else {
        await api(`/projects/${projectId}/${kind}`, 'POST')
        setSync(await api<Sync>(`/projects/${projectId}/sync`))
      }
    } catch (e) { setError(e instanceof Error ? e.message : 'Falha ao executar a operação.') }
    finally { setBusy(false) }
  }
  const running = sync?.latest?.status === 'running'
  const rows = (data?.sprints || []).filter(row => {
    const checked = selection === null || selection.includes(row.id)
    return selectionMode === 'include' ? checked : !checked
  })
  function changeSelectionMode(mode: 'include' | 'exclude') {
    if (mode === selectionMode) return
    setSelection(previous => (data?.sprints || []).filter(row => !(previous === null || previous.includes(row.id))).map(row => row.id))
    setSelectionMode(mode)
  }
  const adoption = data?.ai_adoption_date || null
  const latest = sync?.latest
  function show(sprint: Sprint, key: MetricName) { setDetail({ sprint, key }); setTicketFilter('') }
  function total(key: MetricName) {
    const included = rows.filter(row => row.window.availability === 'available')
    return included.length && included.every(row => row.metrics[key].value !== null) ? included.reduce((sum, row) => sum + row.metrics[key].value!, 0) : null
  }

  return <div className="dashboard">
    <section className="panel sync-panel"><div className="dashboard-section"><div><h2>Histórico do projeto</h2><p className="hint">Última sincronização publicada: {date(sync?.last_success?.collected_at)}</p></div>
      <div className="actions"><button className="primary" disabled={busy || running} onClick={() => action('sync')}>{running ? 'Sincronizando…' : 'Sincronizar agora'}</button>
        {latest && ['failed', 'interrupted'].includes(latest.status) && <button disabled={busy} onClick={() => action('sync/resume')}>Retomar coleta</button>}
        <button disabled={busy || running || !data || data.state !== 'available'} onClick={() => action('recalculate')}>Recalcular indicadores</button></div></div>
      {latest && <div className="sync-info" role="status"><strong>{statusLabels[latest.status] || latest.status}</strong> · {latest.status === 'succeeded' ? 'Base atualizada' : stageLabels[latest.checkpoint.stage] || latest.checkpoint.stage}
        {latest.checkpoint.total !== undefined && <> · {latest.checkpoint.read || 0}/{latest.checkpoint.total} históricos · {latest.checkpoint.reused || 0} reaproveitados</>}
        {running && latest.checkpoint.total ? <progress max={latest.checkpoint.total} value={latest.checkpoint.read || 0} aria-label="Progresso da sincronização" /> : null}
      </div>}
      {latest?.error_code && <div className="alert error" role="alert">{latest.error_code} {sync?.last_success ? 'Os resultados abaixo usam a última base publicada; a tentativa mais recente não foi concluída.' : 'Ainda não existe uma base publicada.'}</div>}
      <p className="hint">A sincronização acontece apenas ao solicitar. A integração faz somente leituras no Jira.</p>
    </section>
    {error && <div className="alert error" role="alert">{error}</div>}
    {!data ? <p role="status">Carregando análise…</p> : data.state !== 'available' ? <section className="panel"><h2>{data.state === 'sync_required' ? 'Sincronize o quadro escolhido' : 'Prepare a primeira análise'}</h2><p className="empty">{data.state === 'sync_required' ? 'O quadro foi alterado na configuração. Sincronize novamente para obter sua base.' : 'Solicite a primeira sincronização para recuperar os tickets e seus históricos. Nenhum indicador é apresentado como zero antes da coleta.'}</p></section> : <>
      <section className="panel sprint-selector"><div className="dashboard-section"><h2>Sprints da análise</h2><div className="actions">
        <button onClick={() => { setSelection(null); setDetail(null) }}>Marcar todas</button>
        <button onClick={() => { setSelection([]); setDetail(null) }}>Desmarcar todas</button>
      </div></div>
        <fieldset className="sprint-filter-mode"><legend>Como filtrar as sprints</legend>
          <label><input type="radio" name="sprint-filter-mode" value="include" checked={selectionMode === 'include'} onChange={() => changeSelectionMode('include')} />Incluir selecionadas</label>
          <label><input type="radio" name="sprint-filter-mode" value="exclude" checked={selectionMode === 'exclude'} onChange={() => changeSelectionMode('exclude')} />Excluir selecionadas</label>
        </fieldset>
        <p className="hint">{selectionMode === 'include' ? 'Marque as sprints que você quer analisar.' : 'Marque as sprints que você não quer analisar. As demais entram na análise.'} Ao trocar de modo, as sprints exibidas são preservadas.</p>
        <div className="sprint-options">{data.sprints.map(row => {
          const checked = selection === null || selection.includes(row.id)
          return <label className="check" key={row.id}><input type="checkbox" checked={checked} onChange={event => {
            const checkedNow = event.target.checked
            setSelection(previous => {
              const ids = previous || data.sprints.map(item => item.id)
              return checkedNow ? [...new Set([...ids, row.id])] : ids.filter(id => id !== row.id)
            })
            setDetail(null)
          }} /><span>{row.name}</span><span className="sprint-state">{{ closed: 'encerrada', active: 'em andamento', future: 'futura' }[row.window.state] || 'indisponível'}</span></label>
        })}</div>
        <p className="hint">Configuração usada: v{data.config_version} · cálculo: {date(data.computed_at)} · {rows.length} de {data.sprints.length} sprints na análise. Para incluir outras sprints, edite a configuração.</p>
      </section>
      {rows.length === 0 ? <section className="panel"><p className="empty">Selecione uma sprint para consultar os indicadores.</p></section> : <>
        <div className="metric-cards">{(['worked', 'completed', 'bugs_total', 'reopened'] as const).map(key => <div className="metric-card" key={key}><span>{labels[key]}</span><strong>{number(total(key))}</strong><small>Soma por sprint · sem períodos futuros{rows.some(row => row.window.partial) ? ' · inclui sprints em andamento' : ''}</small></div>)}</div>
        <Evolution rows={rows} adoption={adoption} />
        <section className="panel"><div className="dashboard-section"><h2>Indicadores por sprint</h2><span className="muted">Clique nos números para conferir os tickets</span></div>
          <div className="table-scroll"><table className="metrics-table"><thead><tr><th>Sprint</th><th>Trabalhadas</th><th>Entregas</th><th>Reabertas</th><th>Bugs</th><th>Novos</th><th>Existentes</th><th>Bugs ÷ trabalho</th></tr></thead><tbody>{rows.map((row, index) => <tr key={row.id}>
            <th scope="row"><strong>{index + 1}. {row.name}</strong><small>{periodLabels[row.ai_period]} · {row.window.partial ? 'Em andamento · parcial' : row.window.state === 'closed' ? 'Encerrada' : 'Futura/indisponível'}</small><small>{date(row.window.start_utc)} → {date(row.window.end_utc)}</small></th>
            {(['worked', 'completed', 'reopened', 'bugs_total', 'bugs_new', 'bugs_existing'] as const).map(key => <td key={key}><button className="metric-link" onClick={() => show(row, key)} aria-label={`${labels[key]} em ${row.name}: ${number(row.metrics[key].value)}`}>{row.metrics[key].value === null ? 'Indisponível' : number(row.metrics[key].value)}</button>{key === 'reopened' && row.reopening_events > (row.metrics.reopened.value || 0) && <small>{row.reopening_events} eventos</small>}</td>)}
            <td>{row.ratio.status === 'not_calculable' ? 'Não calculável' : number(row.ratio.value, 2)}</td>
          </tr>)}</tbody></table></div>
        </section>
        {detail && <section className="panel ticket-details" aria-label="Tickets do indicador"><div className="dashboard-section"><div><h2>{labels[detail.key]}</h2><p className="hint">{detail.sprint.name} · {number(detail.sprint.metrics[detail.key].value)}{detail.sprint.metrics[detail.key].value === null ? ` · ${detail.sprint.metrics[detail.key].known_count} tickets com evidência disponível; total não certificado` : ' tickets'}</p></div><button onClick={() => setDetail(null)}>Fechar detalhes</button></div>
          {!!detail.sprint.metrics[detail.key].limitations.length && <details open><summary>Limitações deste indicador ({detail.sprint.metrics[detail.key].limitations.length})</summary><ul>{detail.sprint.metrics[detail.key].limitations.map((item, index) => <li key={index}>{item.ticket ? `${item.ticket}: ` : ''}{item.reason}</li>)}</ul></details>}
          <label>Filtrar tickets por chave<input value={ticketFilter} onChange={event => setTicketFilter(event.target.value)} placeholder="Chave do ticket" /></label>
          <div className="table-scroll"><table><thead><tr><th>Ticket no Jira</th><th>Tipo</th><th>Eventos de origem</th></tr></thead><tbody>{detail.sprint.metrics[detail.key].tickets.filter(ticket => ticket.key.toLowerCase().includes(ticketFilter.toLowerCase())).map(ticket => <tr key={ticket.id}><td><a href={ticket.url} target="_blank" rel="noreferrer">{ticket.key} ↗</a></td><td>{{ task: 'Tarefa', subtask: 'Subtarefa', bug: 'Bug' }[ticket.kind] || ticket.kind}</td><td>{ticket.events?.map(event => <div key={`${event.history_id}-${event.at}`}>{date(event.at)} · {event.from_name || event.from} → {event.to_name || event.to}</div>) || 'Participação e intervalos históricos do ticket.'}</td></tr>)}</tbody></table></div>
          {!detail.sprint.metrics[detail.key].tickets.length && <p className="empty">{detail.sprint.metrics[detail.key].value === 0 ? 'Nenhum ticket atende a este indicador nesta sprint.' : 'Não há tickets verificáveis para listar neste indicador.'}</p>}
        </section>}
        <Comparison rows={rows} adoption={adoption} onConfigure={onConfigure} />
      </>}
      <details className="panel limitations"><summary>Escopo da coleta e limitações ({data.limitations?.length || 0})</summary><ul>{data.limitations?.map((item, index) => <li key={index}>{item}</li>)}</ul><p className="hint">Datas exibidas em America/Sao_Paulo. Intervalos incluem o início e excluem o fim. “Indisponível” não significa ausência de atividade.</p></details>
    </>}
  </div>
}
