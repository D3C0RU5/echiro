import { useEffect, useState } from 'react'

type Health = { status: string; service: string }

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch('/api/health')
      .then((response) => {
        if (!response.ok) throw new Error('API indisponível')
        return response.json() as Promise<Health>
      })
      .then(setHealth)
      .catch(() => setError(true))
  }, [])

  return (
    <main className="container">
      <div className="brand">
        <img src={`${import.meta.env.BASE_URL}logo-inverted.svg`} alt="" width="44" height="44" />
        <span>echiro</span>
      </div>
      <h1>Seu monorepo está pronto.</h1>
      <p>React com TypeScript no frontend. Python com FastAPI no backend.</p>
      <div className="status" role="status">
        <span className={`indicator ${health ? 'online' : ''}`} />
        {health ? `API conectada: ${health.service}` : error ? 'API indisponível' : 'Conectando à API...'}
      </div>
    </main>
  )
}

export default App
