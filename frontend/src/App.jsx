import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './App.css'

// API Configuration
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// API Helper
class API {
  static async request(endpoint, options = {}) {
    const token = localStorage.getItem('token')
    const headers = {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...options.headers,
    }

    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
    })

    if (response.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }

    const data = await response.json()
    if (!response.ok) {
      throw new Error(data.detail || 'Request failed')
    }
    return data
  }

  static async login(email, password) {
    const data = await this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    return data
  }

  static async register(email, password, full_name) {
    const data = await this.request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name }),
    })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    return data
  }

  static async getConfig() { return await this.request('/api/config') }
  static async updateConfig(config) {
    return await this.request('/api/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    })
  }
  static async getJobQueue() { return await this.request('/api/jobs/queue') }
  static async triggerJobSearch() { return await this.request('/api/jobs/search', { method: 'POST' }) }
  static async getApplications() { return await this.request('/api/applications') }
  static async startApplications() { return await this.request('/api/applications/start', { method: 'POST' }) }

  static async uploadResume(file) {
    const formData = new FormData()
    formData.append('file', file)
    const token = localStorage.getItem('token')
    const response = await fetch(`${API_URL}/api/resume/upload`, {
      method: 'POST',
      headers: { ...(token && { 'Authorization': `Bearer ${token}` }) },
      body: formData,
    })
    if (!response.ok) {
      const data = await response.json()
      throw new Error(data.detail || 'Upload failed')
    }
    return await response.json()
  }
}

// Auth Context
const AuthContext = React.createContext()

function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    try {
      const storedUser = localStorage.getItem('user')
      if (storedUser) setUser(JSON.parse(storedUser))
    } catch (err) {
      console.error('Auth sync failed:', err)
      localStorage.clear()
    }
    setLoading(false)
  }, [])

  const logout = () => {
    localStorage.clear()
    setUser(null)
    window.location.href = '/login'
  }

  return (
    <AuthContext.Provider value={{ user, setUser, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

// Navigation Bar
function Navbar() {
  const { user, logout } = React.useContext(AuthContext)
  const path = window.location.pathname

  return (
    <nav className="navbar">
      <div className="nav-brand">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
        </svg>
        <span>JobAgent.ai</span>
      </div>
      <div className="nav-links">
        <a href="/" className={path === '/' ? 'active' : ''}>Dashboard</a>
        <a href="/queue" className={path === '/queue' ? 'active' : ''}>Queue</a>
        <a href="/applications" className={path === '/applications' ? 'active' : ''}>History</a>
        <a href="/config" className={path === '/config' ? 'active' : ''}>Settings</a>
      </div>
      <div className="nav-user">
        <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{user?.full_name}</span>
        <button className="btn btn-secondary" onClick={logout} style={{ padding: '0.4rem 0.8rem', fontSize: '0.75rem' }}>Logout</button>
      </div>
    </nav>
  )
}

function ProtectedRoute({ children }) {
  const { user, loading } = React.useContext(AuthContext)
  if (loading) return <div className="loading shimmer">Syncing...</div>
  if (!user) return <Navigate to="/login" />
  return <>{children}</>
}

// Login Page
function LoginPage() {
  const { setUser } = React.useContext(AuthContext)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState('')
  const [isRegister, setIsRegister] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const data = isRegister ? await API.register(email, password, fullName) : await API.login(email, password)
      setUser(data.user)
      window.location.href = '/'
    } catch (err) { setError(err.message) }
  }

  return (
    <div className="login-container">
      <div className="login-card glass">
        <div style={{ marginBottom: '2rem' }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
          </svg>
        </div>
        <h1>{isRegister ? 'Start Your Journey' : 'Agent Portal'}</h1>
        <p style={{ color: 'var(--text-muted)', marginBottom: '2.5rem' }}>{isRegister ? 'Join the automation revolution' : 'Access your command center'}</p>
        {error && <div className="error-message glass" style={{ borderColor: 'var(--danger)', color: 'var(--danger)', background: 'rgba(239, 68, 68, 0.1)', padding: '0.75rem', marginBottom: '1.5rem', fontSize: '0.9rem' }}>{error}</div>}
        <form onSubmit={handleSubmit}>
          {isRegister && <div className="form-group"><input type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} required placeholder="Full Name" /></div>}
          <div className="form-group"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="Email address" /></div>
          <div className="form-group"><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="Password" /></div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%', padding: '1rem' }}>{isRegister ? 'Create Account' : 'Sign In'}</button>
        </form>
        <p style={{ marginTop: '2.5rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          {isRegister ? 'Already registered?' : 'Need an account?'} <a href="#" onClick={(e) => { e.preventDefault(); setIsRegister(!isRegister); }} style={{ color: 'var(--primary)', fontWeight: '600', textDecoration: 'none' }}>{isRegister ? 'Sign In' : 'Join Now'}</a>
        </p>
      </div>
    </div>
  )
}

import LiveFeed from './components/LiveFeed';

// Dashboard
function Dashboard() {
  const [stats, setStats] = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [actionStatus, setActionStatus] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  useEffect(() => {
    async function fetchData() {
      try {
        const [statsData, summaryData] = await Promise.all([API.request('/api/applications/stats'), API.request('/api/reports/summary')])
        setStats(statsData)
        setSummary(summaryData)
      } catch (err) { console.error('Dashboard fetch failed:', err) }
      finally { setLoading(false) }
    }
    fetchData()
  }, [])

  const handleAction = async (method, name) => {
    setActionLoading(true)
    setActionStatus(`Initiating ${name}...`)
    try {
      const res = await method()
      setActionStatus(`✓ ${res.message}`)
      setTimeout(() => setActionStatus(''), 5000)
    } catch (err) {
      setActionStatus(`✗ ${err.message}`)
    }
    setActionLoading(false)
  }

  if (loading) return <div className="loading shimmer" style={{ padding: '4rem' }}>Synchronizing...</div>

  return (
    <div className="dashboard">
      <div className="bento-header" style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 className="dashboard-title" style={{ marginBottom: '0.25rem' }}>Command Center</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Automated Talent Acquisition System v1.0</p>
        </div>
        <div className="glass" style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.85rem' }}>
          <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)', boxShadow: '0 0 8px var(--success)' }}></span>
          System Online
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card glass glass-hover">
          <div className="stat-value">{summary?.total_applications || 0}</div>
          <div className="stat-label">Total Applied</div>
        </div>
        <div className="stat-card glass glass-hover">
          <div className="stat-value">{summary?.jobs_in_queue || 0}</div>
          <div className="stat-label">In Queue</div>
        </div>
        <div className="stat-card glass glass-hover">
          <div className="stat-value">{summary?.applications_today || 0}</div>
          <div className="stat-label">Applied Today</div>
        </div>
        <div className="stat-card glass glass-hover">
          <div className="stat-value">{stats?.success_rate?.toFixed(0) || 0}%</div>
          <div className="stat-label">Success Rate</div>
        </div>
      </div>

      <div className="dashboard-grid" style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '1.5rem', marginTop: '1.5rem' }}>
        <div className="dashboard-left" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <LiveFeed API={API} />

          <div className="glass" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '1rem' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
              </svg>
              System Parameters
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
              <div className="param-item">
                <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase' }}>Concurrency</div>
                <div style={{ color: 'var(--primary)', fontWeight: '600' }}>Active</div>
              </div>
              <div className="param-item">
                <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase' }}>Engine</div>
                <div style={{ color: 'var(--primary)', fontWeight: '600' }}>Playwright</div>
              </div>
              <div className="param-item">
                <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase' }}>Security</div>
                <div style={{ color: 'var(--primary)', fontWeight: '600' }}>JWT Active</div>
              </div>
            </div>
          </div>
        </div>

        <div className="dashboard-right" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="glass" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginBottom: '1.25rem', fontSize: '1rem' }}>Agent Controls</h3>
            {actionStatus && (
              <div style={{
                marginBottom: '1rem',
                fontSize: '0.85rem',
                padding: '0.75rem',
                borderRadius: '8px',
                background: actionStatus.startsWith('✓') ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                color: actionStatus.startsWith('✓') ? 'var(--success)' : 'var(--danger)',
                border: `1px solid ${actionStatus.startsWith('✓') ? 'var(--success)' : 'var(--danger)'}`
              }}>
                {actionStatus}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <button
                className="btn btn-primary"
                onClick={() => handleAction(API.triggerJobSearch, 'Candidate Scan')}
                disabled={actionLoading}
                style={{ width: '100%', height: '3.5rem', fontWeight: '600' }}
              >
                {actionLoading && actionStatus.includes('Scan') ? 'Scanning...' : 'Scan Candidates'}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => handleAction(API.startApplications, 'Agent Deployment')}
                disabled={actionLoading}
                style={{ width: '100%', height: '3.5rem', fontWeight: '600', background: 'rgba(99, 102, 241, 0.1)', color: 'var(--secondary)' }}
              >
                {actionLoading && actionStatus.includes('Deploy') ? 'Deploying...' : 'Deploy Agent'}
              </button>
            </div>
          </div>

          <div className="glass" style={{ padding: '1.5rem', flex: 1 }}>
            <h3 style={{ marginBottom: '1rem', fontSize: '1rem' }}>Connectivity</h3>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              <div style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--success)' }}></span>
                API Services: 200 ms
              </div>
              <div style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--success)' }}></span>
                DB Latency: 12 ms
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--primary)' }}></span>
                Scraper: Idle
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// Configuration Page
function ConfigurationPage() {
  const [config, setConfig] = useState(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    API.getConfig().then(setConfig).catch(console.error)
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await API.updateConfig(config)
      setMessage('✓ Saved')
      setTimeout(() => setMessage(''), 3000)
    } catch (err) { setMessage('✗ Error') }
    setSaving(false)
  }

  if (!config) return <div className="loading shimmer">Loading Profile...</div>

  return (
    <div className="page glass">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <h1>Settings</h1>
        <button onClick={handleSave} disabled={saving} className="btn btn-primary">{saving ? '...' : 'Save Changes'}</button>
      </div>
      {message && <div style={{ color: message.startsWith('✓') ? 'var(--success)' : 'var(--danger)', marginBottom: '1rem' }}>{message}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '2rem' }}>
        <div className="config-section">
          <h3>Personal Profile</h3>
          <div className="form-group"><label>Full Name</label><input type="text" value={config.personal_info.name} onChange={(e) => setConfig({ ...config, personal_info: { ...config.personal_info, name: e.target.value } })} /></div>
          <div className="form-group"><label>Email</label><input type="email" value={config.personal_info.email} onChange={(e) => setConfig({ ...config, personal_info: { ...config.personal_info, email: e.target.value } })} /></div>
          <div className="form-group"><label>Phone</label><input type="text" value={config.personal_info.phone} onChange={(e) => setConfig({ ...config, personal_info: { ...config.personal_info, phone: e.target.value } })} /></div>
          <div className="form-group">
            <label>Resume (PDF)</label>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{config.personal_info.resume_path ? '📄 Attached' : 'No file'}</span>
              <input type="file" onChange={async (e) => {
                if (e.target.files[0]) {
                  const data = await API.uploadResume(e.target.files[0])
                  setConfig({ ...config, personal_info: { ...config.personal_info, resume_path: data.path } })
                }
              }} />
            </div>
          </div>
        </div>
        <div className="config-section">
          <h3>Target Specs</h3>
          <div className="form-group"><label>Job Keywords</label><input type="text" value={config.search.keywords.join(', ')} onChange={(e) => setConfig({ ...config, search: { ...config.search, keywords: e.target.value.split(',').map(k => k.trim()) } })} /></div>
          <div className="form-group"><label>Preferred Locations</label><input type="text" value={config.search.locations.join(', ')} onChange={(e) => setConfig({ ...config, search: { ...config.search, locations: e.target.value.split(',').map(l => l.trim()) } })} /></div>
        </div>
      </div>
    </div>
  )
}

// Queue
function JobQueuePage() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    API.getJobQueue().then(d => setJobs(d.jobs)).finally(() => setLoading(false)).catch(console.error)
  }, [])

  return (
    <div className="page glass">
      <h1>Deployment Queue</h1>
      <div className="table-container" style={{ marginTop: '2rem' }}>
        <table>
          <thead><tr><th>Job Title</th><th>Company</th><th>Score</th><th>Status</th></tr></thead>
          <tbody>
            {jobs.map(j => (
              <tr key={j.id}>
                <td style={{ fontWeight: '500' }}>{j.title}</td>
                <td style={{ color: 'var(--text-muted)' }}>{j.company}</td>
                <td><span style={{ color: 'var(--primary)', fontWeight: '600' }}>{(j.match_score * 100).toFixed(0)}%</span></td>
                <td><span className={`status-badge status-${j.status}`}>{j.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// History
function ApplicationsPage() {
  const [apps, setApps] = useState([])
  useEffect(() => { API.getApplications().then(d => setApps(d.applications)).catch(console.error) }, [])
  return (
    <div className="page glass">
      <h1>Execution Logs</h1>
      <div className="table-container" style={{ marginTop: '2rem' }}>
        <table>
          <thead><tr><th>Timestamp</th><th>Job</th><th>Company</th><th>Outcome</th></tr></thead>
          <tbody>
            {apps.map(a => (
              <tr key={a.id}>
                <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{new Date(a.applied_at).toLocaleString()}</td>
                <td>{a.job.title}</td>
                <td>{a.job.company}</td>
                <td><span className={`status-badge status-${a.status}`}>{a.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="app">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/*" element={<ProtectedRoute><Navbar /><main className="content"><Routes><Route path="/" element={<Dashboard />} /><Route path="/queue" element={<JobQueuePage />} /><Route path="/applications" element={<ApplicationsPage />} /><Route path="/config" element={<ConfigurationPage />} /><Route path="*" element={<Navigate to="/" />} /></Routes></main></ProtectedRoute>} />
          </Routes>
        </div>
      </AuthProvider>
    </BrowserRouter>
  )
}
