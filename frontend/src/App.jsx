import { useCallback, useEffect, useRef, useState } from 'react'
import { api, setUnauthorizedHandler } from './api.js'
import { relative, setUsdInr } from './format.js'
import Activity from './pages/Activity.jsx'
import Keys from './pages/Keys.jsx'
import Logs from './pages/Logs.jsx'

const TABS = [
  { key: 'activity', label: 'Activity' },
  { key: 'logs', label: 'Logs' },
  { key: 'keys', label: 'Keys' },
]

function readStored(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback
  } catch {
    return fallback
  }
}

function writeStored(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* storage unavailable: preference just won't persist */
  }
}

function useHashTab() {
  const get = () => {
    const h = window.location.hash.slice(1)
    return TABS.some((t) => t.key === h) ? h : 'activity'
  }
  const [tab, setTab] = useState(get)
  useEffect(() => {
    const onHash = () => setTab(get())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const go = (key) => {
    window.location.hash = key
    setTab(key)
  }
  return [tab, go]
}

function Login({ onLoggedIn }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api('/login', { method: 'POST', body: { username, password } })
      onLoggedIn()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <form className="card login-card" onSubmit={submit}>
        <h1>OpenRouter Usage</h1>
        <label className="field">
          <span>Username</span>
          <input type="text" autoFocus autoComplete="username" autoCapitalize="none" spellCheck={false}
            value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="error-banner">{error}</div>}
        <button type="submit" className="primary" disabled={busy || !username || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}

function SyncStatus({ status, onSyncNow }) {
  if (!status) return null
  const busy = status.phase && status.phase !== 'idle'
  let text
  if (!status.backfill_done) {
    text = status.backfill_cursor
      ? `Importing history… (at ${new Date(status.backfill_cursor * 1000).toLocaleDateString()})`
      : 'Importing history…'
  } else if (busy) {
    text = 'Syncing…'
  } else {
    text = `Synced ${relative(status.last_success_at || status.synced_to)}`
  }
  return (
    <div className="sync-status">
      <span className={`sync-dot${status.last_error ? ' error' : busy ? ' busy' : ''}`} aria-hidden="true" />
      <span title={status.last_error || `${status.generations.toLocaleString('en-US')} requests stored`}>
        {status.last_error ? 'Last sync failed' : text}
      </span>
      <button type="button" className="ghost small" onClick={onSyncNow} disabled={busy}>Sync now</button>
    </div>
  )
}

function ThemeToggle() {
  const [theme, setTheme] = useState(() => readStored('theme', 'auto'))
  useEffect(() => {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
    writeStored('theme', theme)
  }, [theme])
  const next = { auto: 'light', light: 'dark', dark: 'auto' }
  const label = { auto: 'Theme: auto', light: 'Theme: light', dark: 'Theme: dark' }
  return (
    <button type="button" className="ghost small" onClick={() => setTheme(next[theme])}>{label[theme]}</button>
  )
}

function Dashboard({ onLogout }) {
  const [tab, setTab] = useHashTab()
  const [range, setRange] = useState('1m')
  const [groupBy, setGroupBy] = useState('api_key')
  const [filters, setFilters] = useState({})
  const [options, setOptions] = useState(null)
  const [sync, setSync] = useState(null)
  const [dataVersion, setDataVersion] = useState(0)
  const lastSuccess = useRef(null)
  const [fx, setFx] = useState(null)

  const pollSync = useCallback(() => {
    api('/sync').then((s) => {
      setSync(s)
      const marker = `${s.last_success_at}|${s.backfill_cursor}|${s.generations}`
      if (lastSuccess.current !== null && lastSuccess.current !== marker) setDataVersion((v) => v + 1)
      lastSuccess.current = marker
    }).catch(() => {})
  }, [])

  useEffect(() => {
    pollSync()
    const busy = sync && (!sync.backfill_done || sync.phase !== 'idle')
    const t = setInterval(pollSync, busy ? 5000 : 30000)
    return () => clearInterval(t)
  }, [pollSync, sync?.backfill_done, sync?.phase]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    api('/options').then(setOptions).catch(() => {})
    api('/fx').then((r) => {
      setUsdInr(r.usd_inr)
      setFx(r)
    }).catch(() => {})
  }, [dataVersion])

  const syncNow = () => api('/sync', { method: 'POST' }).then(() => setTimeout(pollSync, 500)).catch(() => {})

  const logout = async () => {
    await api('/logout', { method: 'POST' }).catch(() => {})
    onLogout()
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">OpenRouter Usage</div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.key} type="button" className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          <SyncStatus status={sync} onSyncNow={syncNow} />
          <ThemeToggle />
          <button type="button" className="ghost small" onClick={logout}>Log out</button>
        </div>
      </header>
      <main>
        {tab === 'activity' && (
          <Activity range={range} setRange={setRange} groupBy={groupBy} setGroupBy={setGroupBy}
            filters={filters} setFilters={setFilters} options={options} dataVersion={dataVersion} />
        )}
        {tab === 'logs' && (
          <Logs filters={filters} setFilters={setFilters} options={options} dataVersion={dataVersion} />
        )}
        {tab === 'keys' && (
          <Keys dataVersion={dataVersion} onOpenKey={(name) => {
            setFilters({ api_key: name })
            setTab('activity')
          }} />
        )}
        {fx?.usd_inr && (
          <p className="fx-note">
            ₹ amounts use 1 USD = ₹{fx.usd_inr.toFixed(2)} (ECB reference rate{fx.date ? `, ${fx.date}` : ''}),
            applied to all dates. Your bank's card rate and forex fees will make the actual charge a little higher.
          </p>
        )}
      </main>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(null)

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthed(false))
    api('/me').then((r) => setAuthed(r.authenticated)).catch(() => setAuthed(false))
  }, [])

  if (authed === null) return null
  if (!authed) return <Login onLoggedIn={() => setAuthed(true)} />
  return <Dashboard onLogout={() => setAuthed(false)} />
}
