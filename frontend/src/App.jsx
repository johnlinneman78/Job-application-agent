import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './App.css'
import LiveFeed from './components/LiveFeed'

// API Configuration
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// API Helper - Self-contained object to avoid unbound 'this' errors
const API = {
  request: async (endpoint, options = {}) => {
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

    let data
    try {
      data = await response.json()
    } catch (err) {
      data = { detail: 'Server response could not be parsed' }
    }

    if (!response.ok) {
      throw new Error(data.detail || 'Request failed')
    }
    return data
  },

  login: async (email, password) => {
    const data = await API.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    return data
  },

  register: async (email, password, full_name) => {
    const data = await API.request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name }),
    })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    return data
  },

  getConfig: () => API.request('/api/config'),

  updateConfig: (config) => API.request('/api/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  }),

  getJobQueue: () => API.request('/api/jobs/queue'),

  triggerJobSearch: () => API.request('/api/jobs/search', {
    method: 'POST'
  }),

  getApplications: () => API.request('/api/applications'),

  startApplications: () => API.request('/api/applications/start', {
    method: 'POST'
  }),

  uploadResume: async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    const token = localStorage.getItem('token')
    const response = await fetch(`${API_URL}/api/resume/upload`, {
      method: 'POST',
      headers: { ...(token && { 'Authorization': `Bearer ${token}` }) },
      body: formData,
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
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
        <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{user?.full_name || user?.email}</span>
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

// Dashboard
function Dashboard() {
  const [stats, setStats] = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [actionStatus, setActionStatus] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  const refreshData = async () => {
    try {
      const [statsData, summaryData] = await Promise.all([
        API.request('/api/applications/stats'),
        API.request('/api/reports/summary')
      ])
      setStats(statsData)
      setSummary(summaryData)
    } catch (err) {
      console.error('Dashboard fetch failed:', err)
    }
  }

  useEffect(() => {
    async function init() {
      await refreshData()
      setLoading(false)
    }
    init()
  }, [])

  const handleAction = async (actionFn, name) => {
    setActionLoading(true)
    setActionStatus(`Initiating ${name}...`)
    try {
      const res = await actionFn()
      setActionStatus(`✓ ${res.message || 'Operation started successfully'}`)
      await refreshData()
      setTimeout(() => setActionStatus(''), 7000)
    } catch (err) {
      setActionStatus(`✗ ${err.message || 'Operation failed'}`)
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) return <div className="loading shimmer" style={{ padding: '4rem' }}>Synchronizing...</div>

  const queueCount = summary?.jobs_in_queue || 0

  return (
    <div className="dashboard">
      <div className="bento-header" style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 className="dashboard-title" style={{ marginBottom: '0.25rem' }}>Command Center</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Automated LinkedIn Application Agent</p>
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
          <div className="stat-value" style={{ color: queueCount > 0 ? 'var(--primary)' : 'inherit' }}>{queueCount}</div>
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
                <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase' }}>Mode</div>
                <div style={{ color: 'var(--primary)', fontWeight: '600' }}>Safe Easy-Apply</div>
              </div>
              <div className="param-item">
                <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase' }}>Engine</div>
                <div style={{ color: 'var(--primary)', fontWeight: '600' }}>Playwright Auth</div>
              </div>
              <div className="param-item">
                <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase' }}>Session</div>
                <div style={{ color: 'var(--success)', fontWeight: '600' }}>LinkedIn Active</div>
              </div>
            </div>
          </div>
        </div>

        <div className="dashboard-right" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="glass" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginBottom: '1.25rem', fontSize: '1.05rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Agent Controls</span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 'normal' }}>
                {queueCount} in queue
              </span>
            </h3>

            {actionStatus && (
              <div style={{
                marginBottom: '1.25rem',
                fontSize: '0.85rem',
                padding: '0.85rem 1rem',
                borderRadius: '8px',
                background: actionStatus.startsWith('✓') ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
                color: actionStatus.startsWith('✓') ? 'var(--success)' : 'var(--danger)',
                border: `1px solid ${actionStatus.startsWith('✓') ? 'var(--success)' : 'var(--danger)'}`,
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}>
                {actionStatus}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {/* START APPLICATIONS BUTTON */}
              <button
                className="btn btn-primary"
                onClick={() => handleAction(API.startApplications, 'Start Applications')}
                disabled={actionLoading}
                style={{
                  width: '100%',
                  height: '3.75rem',
                  fontWeight: '700',
                  fontSize: '1rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.75rem',
                  background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)',
                  boxShadow: '0 4px 20px rgba(6, 182, 212, 0.35)',
                  cursor: actionLoading ? 'not-allowed' : 'pointer'
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                {actionLoading && actionStatus.includes('Start Applications') ? 'Submitting Applications...' : 'Start Applications'}
              </button>

              {/* SEARCH & QUEUE JOBS BUTTON */}
              <button
                className="btn btn-secondary"
                onClick={() => handleAction(API.triggerJobSearch, 'Job Search')}
                disabled={actionLoading}
                style={{
                  width: '100%',
                  height: '3.5rem',
                  fontWeight: '600',
                  fontSize: '0.95rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.6rem',
                  background: 'rgba(99, 102, 241, 0.12)',
                  color: 'var(--text-main)',
                  border: '1px solid rgba(99, 102, 241, 0.3)'
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8"></circle>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
                {actionLoading && actionStatus.includes('Job Search') ? 'Scanning LinkedIn...' : 'Search & Queue Jobs'}
              </button>
            </div>

            {queueCount === 0 && (
              <div style={{ marginTop: '1.25rem', padding: '0.85rem', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                💡 <strong>Step 1:</strong> Click <strong>"Search & Queue Jobs"</strong> to discover and score matching openings on LinkedIn.<br/>
                💡 <strong>Step 2:</strong> Click <strong>"Start Applications"</strong> to auto-apply with your updated resume!
              </div>
            )}
          </div>

          <div className="glass" style={{ padding: '1.5rem', flex: 1 }}>
            <h3 style={{ marginBottom: '1rem', fontSize: '1rem' }}>Connectivity</h3>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              <div style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--success)' }}></span>
                API Backend: Online (Port 8000)
              </div>
              <div style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--success)' }}></span>
                LinkedIn Auth: Active Session
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--primary)' }}></span>
                Safety Guard: Resume-Only Verified
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
      setMessage('✓ Saved successfully')
      setTimeout(() => setMessage(''), 3000)
    } catch (err) {
      setMessage(`✗ Error: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  if (!config) return <div className="loading shimmer">Loading Profile...</div>

  return (
    <div className="page glass">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <h1>Settings</h1>
        <button onClick={handleSave} disabled={saving} className="btn btn-primary">{saving ? 'Saving...' : 'Save Changes'}</button>
      </div>
      {message && <div style={{ color: message.startsWith('✓') ? 'var(--success)' : 'var(--danger)', marginBottom: '1rem' }}>{message}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '2rem' }}>
        <div className="config-section">
          <h3>Personal Profile</h3>
          <div className="form-group"><label>Full Name</label><input type="text" value={config.personal_info?.name || ''} onChange={(e) => setConfig({ ...config, personal_info: { ...config.personal_info, name: e.target.value } })} /></div>
          <div className="form-group"><label>Email</label><input type="email" value={config.personal_info?.email || ''} onChange={(e) => setConfig({ ...config, personal_info: { ...config.personal_info, email: e.target.value } })} /></div>
          <div className="form-group"><label>Phone</label><input type="text" value={config.personal_info?.phone || ''} onChange={(e) => setConfig({ ...config, personal_info: { ...config.personal_info, phone: e.target.value } })} /></div>
          <div className="form-group">
            <label>Resume (PDF)</label>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{config.personal_info?.resume_path ? '📄 Attached' : 'No file'}</span>
              <input type="file" accept=".pdf" onChange={async (e) => {
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
          <div className="form-group"><label>Job Keywords</label><input type="text" value={(config.search?.keywords || []).join(', ')} onChange={(e) => setConfig({ ...config, search: { ...config.search, keywords: e.target.value.split(',').map(k => k.trim()) } })} /></div>
          <div className="form-group"><label>Preferred Locations</label><input type="text" value={(config.search?.locations || []).join(', ')} onChange={(e) => setConfig({ ...config, search: { ...config.search, locations: e.target.value.split(',').map(l => l.trim()) } })} /></div>
        </div>
      </div>
    </div>
  )
}

// Queue Page
function JobQueuePage() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionStatus, setActionStatus] = useState('')

  const loadQueue = () => {
    setLoading(true)
    API.getJobQueue()
      .then(d => setJobs(d.jobs || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadQueue()
  }, [])

  const handleStartApps = async () => {
    setActionLoading(true)
    setActionStatus('Initiating application submissions...')
    try {
      const res = await API.startApplications()
      setActionStatus(`✓ ${res.message || 'Applications started in background'}`)
      loadQueue()
      setTimeout(() => setActionStatus(''), 7000)
    } catch (err) {
      setActionStatus(`✗ ${err.message || 'Failed to start applications'}`)
    } finally {
      setActionLoading(false)
    }
  }

  const queuedCount = jobs.filter(j => j.status === 'queued').length

  return (
    <div className="page glass">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h1>Deployment Queue</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            Opportunities ready for automated submission
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={handleStartApps}
          disabled={actionLoading || queuedCount === 0}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem',
            padding: '0.75rem 1.5rem',
            fontWeight: '600',
            fontSize: '0.9rem'
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
          {actionLoading ? 'Starting...' : `Start Applications (${queuedCount} queued)`}
        </button>
      </div>

      {actionStatus && (
        <div style={{
          marginBottom: '1.5rem',
          padding: '0.75rem 1rem',
          borderRadius: '8px',
          background: actionStatus.startsWith('✓') ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
          color: actionStatus.startsWith('✓') ? 'var(--success)' : 'var(--danger)',
          border: `1px solid ${actionStatus.startsWith('✓') ? 'var(--success)' : 'var(--danger)'}`,
          fontSize: '0.85rem'
        }}>
          {actionStatus}
        </div>
      )}

      {loading ? (
        <div className="loading shimmer" style={{ padding: '3rem', textAlign: 'center' }}>Loading Queue...</div>
      ) : jobs.length === 0 ? (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <p style={{ marginBottom: '1rem', fontSize: '1.1rem' }}>No jobs in the queue yet.</p>
          <p style={{ fontSize: '0.9rem' }}>Go to the <strong>Dashboard</strong> and click <strong>"Search & Queue Jobs"</strong> to discover matching jobs from LinkedIn.</p>
        </div>
      ) : (
        <div className="table-container" style={{ marginTop: '1rem' }}>
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
      )}
    </div>
  )
}

// History Page
function ApplicationsPage() {
  const [apps, setApps] = useState([])
  useEffect(() => { API.getApplications().then(d => setApps(d.applications || [])).catch(console.error) }, [])
  return (
    <div className="page glass">
      <h1>Execution Logs</h1>
      <div className="table-container" style={{ marginTop: '2rem' }}>
        <table>
          <thead><tr><th>Timestamp</th><th>Job</th><th>Company</th><th>Outcome</th></tr></thead>
          <tbody>
            {apps.length === 0 ? (
              <tr><td colSpan="4" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '2rem' }}>No application submissions logged yet.</td></tr>
            ) : (
              apps.map(a => (
                <tr key={a.id}>
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{new Date(a.applied_at).toLocaleString()}</td>
                  <td>{a.job.title}</td>
                  <td>{a.job.company}</td>
                  <td><span className={`status-badge status-${a.status}`}>{a.status}</span></td>
                </tr>
              ))
            )}
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
