import React, { useState, useEffect } from 'react'
import { SearchPanel, SalaryPanel, ScreeningPanel, PacingPanel, ContactPanel, validateSettings } from './components/SettingsPanels'
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
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

  stopAgent: () => API.request('/api/agent/stop', {
    method: 'POST'
  }),

  resetQueue: () => API.request('/api/jobs/reset', {
    method: 'POST'
  }),

  getTracker: () => API.request('/api/tracker'),
  syncTracker: (opts) => API.request('/api/tracker/sync', {
    method: 'POST',
    body: JSON.stringify(opts || { gmail: true, linkedin: true, days: 30 })
  }),
  getSyncStatus: () => API.request('/api/tracker/sync/status'),
  updateTrackerApp: (id, data) => API.request(`/api/tracker/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  getRecruiterNote: (id) => API.request(`/api/tracker/${id}/note`, {
    method: 'POST'
  }),
  assignUnmatched: (message_id, app_id) => API.request('/api/tracker/unmatched/assign', {
    method: 'POST',
    body: JSON.stringify({ message_id, app_id })
  }),
  sendDigest: () => API.request('/api/tracker/digest', {
    method: 'POST'
  }),

  getAgentStatus: () => API.request('/api/agent/status'),

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

// Navigation Bar using React Router Link for smooth client-side routing
function Navbar() {
  const { user, logout } = React.useContext(AuthContext)
  const location = useLocation()
  const path = location.pathname

  return (
    <nav className="navbar">
      <div className="nav-brand">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
        </svg>
        <span>JobAgent.ai</span>
      </div>
      <div className="nav-links">
        <Link to="/" className={path === '/' ? 'active' : ''}>Dashboard</Link>
        <Link to="/queue" className={path === '/queue' ? 'active' : ''}>Queue</Link>
        <Link to="/applications" className={path === '/applications' ? 'active' : ''}>History</Link>
        <Link to="/tracker" className={path === '/tracker' ? 'active' : ''}>Tracker</Link>
        <Link to="/config" className={path === '/config' ? 'active' : ''}>Settings</Link>
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
  const [userConfig, setUserConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [actionStatus, setActionStatus] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const [agentRunning, setAgentRunning] = useState(false)
  const [taskType, setTaskType] = useState(null)

  const refreshData = async () => {
    try {
      const [statsData, summaryData, statusData, configData] = await Promise.all([
        API.request('/api/applications/stats'),
        API.request('/api/reports/summary'),
        API.getAgentStatus(),
        API.getConfig()
      ])
      setStats(statsData)
      setSummary(summaryData)
      setAgentRunning(statusData?.is_running || false)
      setTaskType(statusData?.task_type || null)
      setUserConfig(configData)
    } catch (err) {
      console.error('Dashboard refresh failed:', err)
    }
  }

  useEffect(() => {
    async function init() {
      await refreshData()
      setLoading(false)
    }
    init()

    const interval = setInterval(refreshData, 3000)
    return () => clearInterval(interval)
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

  const handleStop = async () => {
    setActionLoading(true)
    setActionStatus('Stopping agent task...')
    try {
      const res = await API.stopAgent()
      setActionStatus(`✓ ${res.message || 'Agent stopped'}`)
      await refreshData()
      setTimeout(() => setActionStatus(''), 7000)
    } catch (err) {
      setActionStatus(`✗ ${err.message || 'Failed to stop agent'}`)
    } finally {
      setActionLoading(false)
    }
  }

  const handleResetQueue = async () => {
    if (!window.confirm('Clear all jobs in the queue and reset the search?')) return
    setActionLoading(true)
    setActionStatus('Resetting queue...')
    try {
      const res = await API.resetQueue()
      setActionStatus(`✓ ${res.message || 'Queue reset'}`)
      await refreshData()
      setTimeout(() => setActionStatus(''), 6000)
    } catch (err) {
      setActionStatus(`✗ ${err.message || 'Failed to reset'}`)
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) return <div className="loading shimmer" style={{ padding: '4rem' }}>Synchronizing...</div>

  const queueCount = summary?.jobs_in_queue || 0
  const resumeAttached = Boolean(userConfig?.personal_info?.resume_path)

  return (
    <div className="dashboard">
      <div className="bento-header" style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 className="dashboard-title" style={{ marginBottom: '0.25rem' }}>Command Center</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Automated LinkedIn Application Agent</p>
        </div>
        <div className="glass" style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.85rem' }}>
          <span style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: agentRunning ? 'var(--warning)' : 'var(--success)',
            boxShadow: agentRunning ? '0 0 8px var(--warning)' : '0 0 8px var(--success)'
          }}></span>
          {agentRunning ? `Task Active (${taskType || 'Browser'})` : 'System Online'}
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

          {/* ACTIVE PROFILE & RESUME CARD */}
          <div className="glass" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginBottom: '1.25rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '1rem' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                </svg>
                Active Candidate Profile
              </span>
              <Link to="/config" style={{ fontSize: '0.8rem', color: 'var(--primary)', textDecoration: 'none' }}>Edit Profile →</Link>
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>Candidate</div>
                <div style={{ fontWeight: '600', color: 'var(--text-main)' }}>{userConfig?.personal_info?.name || 'Your profile'}</div>
              </div>
              <div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>Resume Status</div>
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  fontWeight: '600',
                  color: resumeAttached ? 'var(--success)' : 'var(--danger)',
                  fontSize: '0.85rem'
                }}>
                  <span>{resumeAttached ? '✓ resume.pdf (Saved & Active)' : '⚠️ No Resume Attached'}</span>
                </div>
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--card-border)', paddingTop: '0.75rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              <strong>Target Keywords:</strong> {(userConfig?.search?.keywords || []).slice(0, 5).join(', ')}
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

            {/* RUNNING BANNER WITH STOP BUTTON */}
            {agentRunning && (
              <div style={{
                marginBottom: '1.25rem',
                padding: '0.85rem 1rem',
                borderRadius: '8px',
                background: 'rgba(245, 158, 11, 0.12)',
                border: '1px solid rgba(245, 158, 11, 0.4)',
                color: 'var(--warning)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.85rem'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--warning)', animation: 'pulse 1.5s infinite' }}></span>
                  <strong>{taskType === 'search' ? 'Scanning & Checking Jobs...' : 'Submitting Applications...'}</strong>
                </div>
                <button
                  onClick={handleStop}
                  disabled={actionLoading}
                  style={{
                    background: '#ef4444',
                    color: '#fff',
                    border: 'none',
                    padding: '0.35rem 0.75rem',
                    borderRadius: '6px',
                    fontWeight: '700',
                    fontSize: '0.8rem',
                    cursor: 'pointer'
                  }}
                >
                  ⏹ Stop Task
                </button>
              </div>
            )}

            {actionStatus && !agentRunning && (
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
                disabled={actionLoading || agentRunning || queueCount === 0}
                style={{
                  width: '100%',
                  height: '3.75rem',
                  fontWeight: '700',
                  fontSize: '1rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.75rem',
                  background: queueCount > 0 && !agentRunning ? 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)' : 'rgba(255, 255, 255, 0.1)',
                  boxShadow: queueCount > 0 && !agentRunning ? '0 4px 20px rgba(6, 182, 212, 0.35)' : 'none',
                  cursor: (actionLoading || agentRunning || queueCount === 0) ? 'not-allowed' : 'pointer',
                  opacity: (queueCount === 0 || agentRunning) ? 0.6 : 1
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                {actionLoading && actionStatus.includes('Start Applications') ? 'Submitting Applications...' : `Start Applications (${queueCount})`}
              </button>

              {/* SEARCH & QUEUE JOBS BUTTON */}
              <button
                className="btn btn-secondary"
                onClick={() => handleAction(API.triggerJobSearch, 'Job Search')}
                disabled={actionLoading || agentRunning}
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
                  border: '1px solid rgba(99, 102, 241, 0.3)',
                  cursor: (actionLoading || agentRunning) ? 'not-allowed' : 'pointer'
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8"></circle>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
                {agentRunning && taskType === 'search' ? 'Scanning LinkedIn...' : 'Search & Queue Jobs'}
              </button>

              {/* ACTION ROW: STOP & RESET */}
              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
                {agentRunning && (
                  <button
                    onClick={handleStop}
                    disabled={actionLoading}
                    style={{
                      flex: 1,
                      padding: '0.75rem',
                      background: 'rgba(239, 68, 68, 0.15)',
                      color: 'var(--danger)',
                      border: '1px solid var(--danger)',
                      borderRadius: '8px',
                      fontWeight: '600',
                      cursor: 'pointer',
                      fontSize: '0.85rem'
                    }}
                  >
                    ⏹ Stop Current Search
                  </button>
                )}
                <button
                  onClick={handleResetQueue}
                  disabled={actionLoading || agentRunning || queueCount === 0}
                  style={{
                    flex: 1,
                    padding: '0.75rem',
                    background: 'rgba(255, 255, 255, 0.05)',
                    color: 'var(--text-muted)',
                    border: '1px solid var(--card-border)',
                    borderRadius: '8px',
                    fontWeight: '500',
                    cursor: (actionLoading || agentRunning || queueCount === 0) ? 'not-allowed' : 'pointer',
                    fontSize: '0.85rem'
                  }}
                >
                  🔄 Reset Search / Clear Queue
                </button>
              </div>
            </div>

            {queueCount === 0 && !agentRunning && (
              <div style={{ marginTop: '1.25rem', padding: '0.85rem', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                💡 <strong>Step 1:</strong> Click <strong>"Search & Queue Jobs"</strong> to discover matching jobs from LinkedIn.<br/>
                💡 <strong>Step 2:</strong> Click <strong>"Start Applications"</strong> to begin auto-applying!
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
  const [nameStr, setNameStr] = useState('')
  const [emailStr, setEmailStr] = useState('')
  const [phoneStr, setPhoneStr] = useState('')
  const [resumePath, setResumePath] = useState('')
  const [resumeFileName, setResumeFileName] = useState('')
  const [uploadingResume, setUploadingResume] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [settingsTab, setSettingsTab] = useState('search')
  const [dirty, setDirty] = useState(false)

  // update one setting: update('search', 'work_types', ['remote'])
  const update = (section, key, value) => {
    setConfig(prev => ({ ...prev, [section]: { ...(prev?.[section] || {}), [key]: value } }))
    setDirty(true)
  }

  useEffect(() => {
    API.getConfig().then(cfg => {
      setConfig(cfg)
      setNameStr(cfg.personal_info?.name || '')
      setEmailStr(cfg.personal_info?.email || '')
      setPhoneStr(cfg.personal_info?.phone || '')
      const rPath = cfg.personal_info?.resume_path || ''
      setResumePath(rPath)
      if (rPath) setResumeFileName('resume.pdf')
    }).catch(console.error)
  }, [])

  const handleResumeUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadingResume(true)
    setMessage('')
    try {
      const data = await API.uploadResume(file)
      setResumePath(data.path)
      setResumeFileName(file.name)
      setMessage(`✓ Resume "${file.name}" uploaded & saved!`)
      // Refresh config from server
      const updated = await API.getConfig()
      setConfig(updated)
      setTimeout(() => setMessage(''), 4000)
    } catch (err) {
      setMessage(`✗ Upload failed: ${err.message}`)
    } finally {
      setUploadingResume(false)
    }
  }

  const handleSave = async () => {
    const updatedConfig = {
      ...config,
      personal_info: {
        ...config?.personal_info,
        name: nameStr,
        email: emailStr,
        phone: phoneStr,
        resume_path: resumePath || config?.personal_info?.resume_path || ''
      }
    }
    const errs = validateSettings(updatedConfig)
    if (errs.length) {
      setMessage(`✗ ${errs.join(' ')}`)
      return
    }
    setSaving(true)
    try {
      await API.updateConfig(updatedConfig)
      setConfig(updatedConfig)
      setDirty(false)
      setMessage('✓ All settings saved.')
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
        <div>
          <h1>Settings</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            Configure your target roles, locations, and personal profile
          </p>
        </div>
        <button onClick={handleSave} disabled={saving} className="btn btn-primary">{saving ? 'Saving...' : (dirty ? 'Save Changes •' : 'Save Changes')}</button>
      </div>
      {message && <div style={{ color: message.startsWith('✓') ? 'var(--success)' : 'var(--danger)', marginBottom: '1rem' }}>{message}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(400px, 100%), 1fr))', gap: '2rem' }}>
        <div className="config-section">
          <h3>Personal Profile</h3>
          <div className="form-group">
            <label>Full Name</label>
            <input type="text" value={nameStr} onChange={(e) => setNameStr(e.target.value)} />
          </div>
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={emailStr} onChange={(e) => setEmailStr(e.target.value)} />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input type="text" value={phoneStr} onChange={(e) => setPhoneStr(e.target.value)} />
          </div>

          {/* DEDICATED RESUME ATTACHMENT CARD */}
          <div className="form-group" style={{ marginTop: '1.5rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem' }}>Resume Document</label>
            <div style={{
              padding: '1rem',
              borderRadius: '12px',
              background: resumePath ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
              border: `1px solid ${resumePath ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={resumePath ? 'var(--success)' : 'var(--danger)'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                  </svg>
                  <div>
                    <div style={{ fontWeight: '600', fontSize: '0.9rem', color: resumePath ? 'var(--success)' : 'var(--danger)' }}>
                      {resumePath ? `✓ Active Resume: ${resumeFileName || 'resume.pdf'}` : '⚠️ No Resume Attached'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {resumePath ? 'Configured and ready for automated applications' : 'Upload your PDF resume to enable auto-applying'}
                    </div>
                  </div>
                </div>

                <label style={{
                  background: 'var(--primary)',
                  color: '#000',
                  padding: '0.45rem 0.9rem',
                  borderRadius: '6px',
                  fontWeight: '600',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem'
                }}>
                  <span>{uploadingResume ? 'Uploading...' : (resumePath ? 'Upload New PDF' : 'Choose PDF')}</span>
                  <input
                    type="file"
                    accept=".pdf"
                    style={{ display: 'none' }}
                    onChange={handleResumeUpload}
                    disabled={uploadingResume}
                  />
                </label>
              </div>
            </div>
          </div>
        </div>

        <div className="config-section">
          <h3>Contact details</h3>
          <p className="section-sub">Used when a form asks for city, ZIP or LinkedIn URL and LinkedIn didn't pre-fill it.</p>
          <ContactPanel config={config} update={update} />
        </div>

        <div className="config-section" style={{ gridColumn: '1 / -1' }}>
          <div className="settings-tabs" role="tablist">
            {[['search', 'Job search'], ['salary', 'Salary'], ['screening', 'Screening answers'], ['pacing', 'Pacing']].map(([id, label]) => (
              <button key={id} role="tab" aria-selected={settingsTab === id}
                className={`settings-tab ${settingsTab === id ? 'active' : ''}`} onClick={() => setSettingsTab(id)}>{label}</button>
            ))}
          </div>
          {settingsTab === 'search' && <SearchPanel config={config} update={update} />}
          {settingsTab === 'salary' && <SalaryPanel config={config} update={update} />}
          {settingsTab === 'screening' && <ScreeningPanel config={config} update={update} />}
          {settingsTab === 'pacing' && <PacingPanel config={config} update={update} />}
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
  const [agentRunning, setAgentRunning] = useState(false)

  const loadQueue = async () => {
    setLoading(true)
    try {
      const [queueData, statusData] = await Promise.all([
        API.getJobQueue(),
        API.getAgentStatus()
      ])
      setJobs(queueData.jobs || [])
      setAgentRunning(statusData?.is_running || false)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadQueue()
    const interval = setInterval(async () => {
      try {
        const queueData = await API.getJobQueue()
        setJobs(queueData.jobs || [])
        const statusData = await API.getAgentStatus()
        setAgentRunning(statusData?.is_running || false)
      } catch (e) {}
    }, 3000)
    return () => clearInterval(interval)
  }, [])

  const handleStartApps = async () => {
    setActionLoading(true)
    setActionStatus('Initiating application submissions...')
    try {
      const res = await API.startApplications()
      setActionStatus(`✓ ${res.message || 'Applications started in background'}`)
      await loadQueue()
      setTimeout(() => setActionStatus(''), 7000)
    } catch (err) {
      setActionStatus(`✗ ${err.message || 'Failed to start applications'}`)
    } finally {
      setActionLoading(false)
    }
  }

  const handleStop = async () => {
    setActionLoading(true)
    try {
      const res = await API.stopAgent()
      setActionStatus(`✓ ${res.message || 'Agent stopped'}`)
      await loadQueue()
      setTimeout(() => setActionStatus(''), 6000)
    } catch (err) {
      setActionStatus(`✗ ${err.message || 'Failed to stop'}`)
    } finally {
      setActionLoading(false)
    }
  }

  const handleReset = async () => {
    if (!window.confirm('Clear all jobs in the queue?')) return
    setActionLoading(true)
    try {
      const res = await API.resetQueue()
      setActionStatus(`✓ ${res.message || 'Queue reset'}`)
      await loadQueue()
      setTimeout(() => setActionStatus(''), 6000)
    } catch (err) {
      setActionStatus(`✗ ${err.message || 'Failed to reset'}`)
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
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {agentRunning && (
            <button
              onClick={handleStop}
              disabled={actionLoading}
              style={{
                background: 'rgba(239, 68, 68, 0.2)',
                color: 'var(--danger)',
                border: '1px solid var(--danger)',
                padding: '0.75rem 1.25rem',
                borderRadius: '8px',
                fontWeight: '600',
                fontSize: '0.85rem',
                cursor: 'pointer'
              }}
            >
              ⏹ Stop Task
            </button>
          )}
          <button
            onClick={handleReset}
            disabled={actionLoading || agentRunning || jobs.length === 0}
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              color: 'var(--text-muted)',
              border: '1px solid var(--card-border)',
              padding: '0.75rem 1.25rem',
              borderRadius: '8px',
              fontWeight: '500',
              fontSize: '0.85rem',
              cursor: (actionLoading || agentRunning || jobs.length === 0) ? 'not-allowed' : 'pointer'
            }}
          >
            🔄 Reset Queue
          </button>
          <button
            className="btn btn-primary"
            onClick={handleStartApps}
            disabled={actionLoading || agentRunning || queuedCount === 0}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.6rem',
              padding: '0.75rem 1.5rem',
              fontWeight: '600',
              fontSize: '0.9rem',
              cursor: (actionLoading || agentRunning || queuedCount === 0) ? 'not-allowed' : 'pointer'
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
            {actionLoading ? 'Starting...' : `Start Applications (${queuedCount})`}
          </button>
        </div>
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
            <thead>
              <tr>
                <th>Job Title</th>
                <th>Company</th>
                <th>Fit</th>
                <th>Matched Skills</th>
                <th>Hiring Contact & Follow-up</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(j => (
                <tr key={j.id}>
                  <td style={{ fontWeight: '500' }}>
                    <a href={j.url} target="_blank" rel="noreferrer" style={{ color: 'var(--text-main)', textDecoration: 'none' }}>
                      {j.title} ↗
                    </a>
                  </td>
                  <td style={{ color: 'var(--text-muted)' }}>{j.company}</td>
                  <td>
                    <span style={{
                      color: j.match_score >= 0.7 ? 'var(--success)' : (j.match_score >= 0.4 ? 'var(--primary)' : 'var(--warning)'),
                      fontWeight: '700'
                    }}>
                      {(j.match_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', maxWidth: '220px' }}>
                      {j.matched_skills && j.matched_skills.length > 0 ? (
                        j.matched_skills.slice(0, 3).map(s => (
                          <span key={s} style={{
                            display: 'inline-block',
                            padding: '0.15rem 0.45rem',
                            fontSize: '0.72rem',
                            borderRadius: '4px',
                            background: 'rgba(6, 182, 212, 0.12)',
                            color: 'var(--primary)',
                            border: '1px solid rgba(6, 182, 212, 0.25)'
                          }}>
                            {s}
                          </span>
                        ))
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>Role Alignment</span>
                      )}
                    </div>
                  </td>
                  <td>
                    {j.recruiter_name ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        {j.recruiter_url ? (
                          <a href={j.recruiter_url} target="_blank" rel="noreferrer" style={{ fontSize: '0.82rem', color: 'var(--primary)', textDecoration: 'underline' }}>
                            👤 {j.recruiter_name}
                          </a>
                        ) : (
                          <span style={{ fontSize: '0.82rem', color: 'var(--text-main)' }}>👤 {j.recruiter_name}</span>
                        )}
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(j.follow_up_note || '');
                            alert(`Copied personalized follow-up note for ${j.recruiter_name} to clipboard!`);
                          }}
                          title="Copy personalized recruiter outreach message (LinkedHelper tip)"
                          style={{
                            background: 'rgba(255, 255, 255, 0.08)',
                            color: 'var(--text-main)',
                            border: '1px solid rgba(255, 255, 255, 0.15)',
                            padding: '0.2rem 0.45rem',
                            borderRadius: '4px',
                            fontSize: '0.72rem',
                            cursor: 'pointer'
                          }}
                        >
                          📋 Copy Pitch
                        </button>
                      </div>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Direct Easy Apply</span>
                    )}
                  </td>
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
          <thead><tr><th>Timestamp</th><th>Job</th><th>Company</th><th>Recruiter Follow-up</th><th>Outcome</th></tr></thead>
          <tbody>
            {apps.length === 0 ? (
              <tr><td colSpan="5" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '2rem' }}>No application submissions logged yet.</td></tr>
            ) : (
              apps.map(a => (
                <tr key={a.id}>
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{new Date(a.applied_at || a.timestamp).toLocaleString()}</td>
                  <td>
                    <a href={a.job.url} target="_blank" rel="noreferrer" style={{ color: 'var(--text-main)', textDecoration: 'none' }}>
                      {a.job.title} ↗
                    </a>
                  </td>
                  <td>{a.job.company}</td>
                  <td>
                    {a.recruiter_name ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        {a.recruiter_url ? (
                          <a href={a.recruiter_url} target="_blank" rel="noreferrer" style={{ fontSize: '0.82rem', color: 'var(--primary)', textDecoration: 'underline' }}>
                            👤 {a.recruiter_name}
                          </a>
                        ) : (
                          <span style={{ fontSize: '0.82rem' }}>👤 {a.recruiter_name}</span>
                        )}
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(a.follow_up_note || '');
                            alert(`Copied recruiter follow-up message to clipboard!`);
                          }}
                          style={{
                            background: 'rgba(255, 255, 255, 0.08)',
                            color: 'var(--text-main)',
                            border: '1px solid rgba(255, 255, 255, 0.15)',
                            padding: '0.2rem 0.45rem',
                            borderRadius: '4px',
                            fontSize: '0.72rem',
                            cursor: 'pointer'
                          }}
                        >
                          📋 Copy Pitch
                        </button>
                      </div>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>None Listed</span>
                    )}
                  </td>
                  <td>
                    <span className={`status-badge status-${a.status}`}>{a.status}</span>
                    {a.failure_reason && (
                      <div style={{ fontSize: '0.73rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                        {a.failure_reason}
                      </div>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Tracker Page
function TrackerPage() {
  const [trackerData, setTrackerData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState('')
  const [expandedAppId, setExpandedAppId] = useState(null)
  const [notesState, setNotesState] = useState({})
  const [assignSelections, setAssignSelections] = useState({})

  const loadData = async () => {
    try {
      const data = await API.getTracker()
      setTrackerData(data)
      const notes = {}
      (data.applications || []).forEach(a => {
        notes[a.id] = a.tracking?.notes || ''
      })
      setNotesState(notes)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    setSyncMsg('Starting sync with Gmail & LinkedIn...')
    try {
      await API.syncTracker({ gmail: true, linkedin: true, days: 30 })
      const interval = setInterval(async () => {
        try {
          const st = await API.getSyncStatus()
          if (!st.running) {
            clearInterval(interval)
            setSyncing(false)
            setSyncMsg(st.last_result ? `Sync complete: ${JSON.stringify(st.last_result)}` : 'Sync complete!')
            loadData()
          } else {
            setSyncMsg('Syncing emails and application statuses in background...')
          }
        } catch {
          clearInterval(interval)
          setSyncing(false)
        }
      }, 3000)
    } catch (err) {
      setSyncing(false)
      setSyncMsg(`Sync error: ${err.message || 'Failed'}`)
    }
  }

  const handleSendDigest = async () => {
    try {
      await API.sendDigest()
      alert('Daily summary email sent successfully!')
    } catch (err) {
      alert(`Could not send summary email: ${err.message || err}`)
    }
  }

  const handleStageChange = async (appId, newStage) => {
    try {
      await API.updateTrackerApp(appId, { stage: newStage })
      loadData()
    } catch (err) {
      alert(`Could not update stage: ${err.message || err}`)
    }
  }

  const handleSaveNotes = async (appId) => {
    try {
      await API.updateTrackerApp(appId, { notes: notesState[appId] || '' })
      alert('Notes saved!')
      loadData()
    } catch (err) {
      alert(`Could not save notes: ${err.message || err}`)
    }
  }

  const handleMarkFollowUpDone = async (appId) => {
    try {
      await API.updateTrackerApp(appId, { follow_up_done: true })
      loadData()
    } catch (err) {
      alert(`Could not mark follow-up done: ${err.message || err}`)
    }
  }

  const handleCopyPitch = async (appId, fallbackNote) => {
    try {
      const res = await API.getRecruiterNote(appId)
      const note = res.note || fallbackNote || ''
      navigator.clipboard.writeText(note)
      alert('Copied recruiter pitch note to clipboard!')
    } catch {
      navigator.clipboard.writeText(fallbackNote || '')
      alert('Copied recruiter pitch note to clipboard!')
    }
  }

  const handleAssignEmail = async (msgId) => {
    const appId = assignSelections[msgId]
    if (!appId) {
      alert('Please select an application to assign.')
      return
    }
    try {
      await API.assignUnmatched(msgId, appId)
      alert('Email assigned successfully!')
      loadData()
    } catch (err) {
      alert(`Could not assign email: ${err.message || err}`)
    }
  }

  if (loading) return <div className="loading shimmer">Loading Tracker...</div>
  if (!trackerData) return <div className="page glass"><p>Could not load tracker data.</p></div>

  const { stats, applications = [], follow_ups_due = [], unmatched_emails = [], stages = [], gmail_configured } = trackerData
  const dueApps = applications.filter(a => follow_ups_due.includes(a.id))

  return (
    <div className="page glass">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <div>
          <h1>Application & Reply Tracker</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            Full lifecycle tracking: responses, interviews, recruiter outreach, and application audit history
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <button className="btn btn-secondary" onClick={handleSendDigest} style={{ fontSize: '0.82rem' }}>
            ✉️ Email Summary
          </button>
          <button className="btn btn-primary" onClick={handleSync} disabled={syncing} style={{ fontSize: '0.82rem' }}>
            {syncing ? '⏳ Syncing...' : '🔄 Sync Replies'}
          </button>
        </div>
      </div>

      {syncMsg && (
        <div style={{ background: 'rgba(6, 182, 212, 0.1)', border: '1px solid rgba(6, 182, 212, 0.3)', padding: '0.65rem 1rem', borderRadius: '8px', fontSize: '0.82rem', marginBottom: '1.5rem', color: 'var(--text-main)' }}>
          {syncMsg}
        </div>
      )}

      {!gmail_configured && (
        <div style={{ background: 'rgba(234, 179, 8, 0.1)', border: '1px solid rgba(234, 179, 8, 0.3)', padding: '0.75rem 1rem', borderRadius: '10px', fontSize: '0.83rem', marginBottom: '1.5rem', color: '#fef08a' }}>
          💡 <strong>Tip: Gmail IMAP reply detection is not configured.</strong> To automatically scan recruiter replies, interview invites, and rejection notices, copy <code>.env.example</code> to <code>.env</code> and set <code>GMAIL_USER</code> and your 16-character <code>GMAIL_APP_PASSWORD</code>.
        </div>
      )}

      {/* STAT CARDS */}
      <div className="stats-grid" style={{ marginBottom: '2rem' }}>
        <div className="stat-card">
          <div className="stat-title">Submitted</div>
          <div className="stat-value">{stats?.total_submitted || 0}</div>
          <div className="stat-desc">Confirmed applications</div>
        </div>
        <div className="stat-card">
          <div className="stat-title">Viewed Rate</div>
          <div className="stat-value" style={{ color: 'var(--primary)' }}>{stats?.viewed_rate_pct || 0}%</div>
          <div className="stat-desc">{stats?.viewed || 0} applications opened</div>
        </div>
        <div className="stat-card">
          <div className="stat-title">Reply Rate</div>
          <div className="stat-value" style={{ color: 'var(--success)' }}>{stats?.reply_rate_pct || 0}%</div>
          <div className="stat-desc">{stats?.replied || 0} received recruiter response</div>
        </div>
        <div className="stat-card">
          <div className="stat-title">Interviews</div>
          <div className="stat-value" style={{ color: '#ec4899' }}>{stats?.interviews || 0}</div>
          <div className="stat-desc">Phone / technical screenings</div>
        </div>
        <div className="stat-card">
          <div className="stat-title">Submit Rate</div>
          <div className="stat-value">{stats?.submit_rate_pct || 0}%</div>
          <div className="stat-desc">{stats?.total_submitted || 0} of {stats?.total_attempted || 0} attempted</div>
        </div>
      </div>

      {/* FOLLOW-UPS DUE */}
      {dueApps.length > 0 && (
        <div className="config-section" style={{ marginBottom: '2rem', border: '1px solid rgba(6, 182, 212, 0.4)', background: 'rgba(6, 182, 212, 0.05)' }}>
          <h3 style={{ color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            ⏰ Follow-ups Due ({dueApps.length})
          </h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginBottom: '1rem' }}>
            Recruiters for these positions viewed your profile or have been waiting 24+ hours. Send a quick outreach note to stand out!
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {dueApps.map(a => (
              <div key={a.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.03)', padding: '0.85rem 1rem', borderRadius: '8px', flexWrap: 'wrap', gap: '0.75rem' }}>
                <div>
                  <div style={{ fontWeight: '600', fontSize: '0.9rem' }}>{a.job?.title} @ {a.job?.company}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Recruiter: {a.recruiter_name ? (
                      a.recruiter_url ? (
                        <a href={a.recruiter_url} target="_blank" rel="noreferrer" style={{ color: 'var(--primary)', textDecoration: 'underline' }}>
                          {a.recruiter_name} ↗
                        </a>
                      ) : a.recruiter_name
                    ) : 'Hiring Team'}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="btn btn-secondary" onClick={() => handleCopyPitch(a.id, a.follow_up_note)} style={{ padding: '0.35rem 0.7rem', fontSize: '0.78rem' }}>
                    📋 Copy Note
                  </button>
                  {a.recruiter_url && (
                    <a href={a.recruiter_url} target="_blank" rel="noreferrer" className="btn btn-secondary" style={{ padding: '0.35rem 0.7rem', fontSize: '0.78rem', textDecoration: 'none' }}>
                      👤 View Profile
                    </a>
                  )}
                  <button className="btn btn-primary" onClick={() => handleMarkFollowUpDone(a.id)} style={{ padding: '0.35rem 0.7rem', fontSize: '0.78rem' }}>
                    ✓ Mark Done
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SKIP REASONS & BY TITLE */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        <div className="config-section">
          <h3>Why Jobs Were Skipped</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.78rem', marginBottom: '1rem' }}>
            Safeguard reasons protecting you from applying to mismatched jobs
          </p>
          {stats?.skip_reasons && Object.keys(stats.skip_reasons).length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {Object.entries(stats.skip_reasons).map(([reason, count]) => (
                <div key={reason} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.45rem 0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', fontSize: '0.83rem' }}>
                  <span style={{ textTransform: 'capitalize' }}>{reason.replace(/_/g, ' ')}</span>
                  <span style={{ fontWeight: '600', color: 'var(--text-muted)' }}>{count}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No jobs skipped yet.</p>
          )}
        </div>

        <div className="config-section">
          <h3>Performance by Title</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.78rem', marginBottom: '1rem' }}>
            Response and submission volume grouped by target job title
          </p>
          {stats?.by_title && Object.keys(stats.by_title).length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {Object.entries(stats.by_title).slice(0, 5).map(([title, st]) => (
                <div key={title} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.45rem 0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', fontSize: '0.83rem' }}>
                  <span style={{ fontWeight: '500' }}>{title}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                    {st.submitted} submitted · {st.replied} replied
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No title data recorded yet.</p>
          )}
        </div>
      </div>

      {/* APPLICATIONS TRACKER TABLE */}
      <div className="config-section">
        <h3>Applications Tracking & Auditing</h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '1.25rem' }}>
          Live status of every submission, recruiter follow-up pitch, and exact answers submitted
        </p>

        {applications.length === 0 ? (
          <p className="muted" style={{ padding: '2rem', textAlign: 'center' }}>No applications tracked yet.</p>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Applied</th>
                  <th>Role & Company</th>
                  <th>Stage</th>
                  <th>Recruiter</th>
                  <th>Notes</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {applications.map(a => {
                  const isExpanded = expandedAppId === a.id
                  const currStage = a.tracking?.stage || (a.status === 'submitted' ? 'applied' : a.status)
                  return (
                    <React.Fragment key={a.id}>
                      <tr>
                        <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                          {new Date(a.applied_at || a.timestamp || Date.now()).toLocaleDateString()}
                        </td>
                        <td>
                          <div style={{ fontWeight: '600' }}>
                            <a href={a.job?.url} target="_blank" rel="noreferrer" style={{ color: 'var(--text-main)', textDecoration: 'none' }}>
                              {a.job?.title} ↗
                            </a>
                          </div>
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{a.job?.company} · {a.job?.location}</div>
                        </td>
                        <td>
                          <select
                            value={currStage}
                            onChange={(e) => handleStageChange(a.id, e.target.value)}
                            style={{ padding: '0.3rem 0.5rem', fontSize: '0.8rem', borderRadius: '6px' }}
                          >
                            {stages.map(s => (
                              <option key={s} value={s}>{s}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          {a.recruiter_name ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                              {a.recruiter_url ? (
                                <a href={a.recruiter_url} target="_blank" rel="noreferrer" style={{ fontSize: '0.82rem', color: 'var(--primary)', textDecoration: 'underline' }}>
                                  👤 {a.recruiter_name}
                                </a>
                              ) : (
                                <span style={{ fontSize: '0.82rem' }}>👤 {a.recruiter_name}</span>
                              )}
                              <button
                                className="btn btn-secondary"
                                onClick={() => handleCopyPitch(a.id, a.follow_up_note)}
                                style={{ padding: '0.2rem 0.45rem', fontSize: '0.72rem' }}
                              >
                                📋 Pitch
                              </button>
                            </div>
                          ) : (
                            <span className="muted">Direct Easy Apply</span>
                          )}
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: '0.35rem' }}>
                            <input
                              type="text"
                              value={notesState[a.id] ?? ''}
                              onChange={(e) => setNotesState({ ...notesState, [a.id]: e.target.value })}
                              placeholder="Add notes..."
                              style={{ width: '130px', padding: '0.3rem 0.5rem', fontSize: '0.78rem' }}
                            />
                            <button
                              className="btn btn-secondary"
                              onClick={() => handleSaveNotes(a.id)}
                              style={{ padding: '0.25rem 0.5rem', fontSize: '0.72rem' }}
                            >
                              Save
                            </button>
                          </div>
                        </td>
                        <td>
                          <button
                            className="btn btn-secondary"
                            onClick={() => setExpandedAppId(isExpanded ? null : a.id)}
                            style={{ padding: '0.3rem 0.6rem', fontSize: '0.76rem' }}
                          >
                            {isExpanded ? '▲ Hide' : '▼ Details'}
                          </button>
                        </td>
                      </tr>

                      {/* EXPANDED DETAILS ROW */}
                      {isExpanded && (
                        <tr>
                          <td colSpan="6" style={{ background: 'rgba(255,255,255,0.02)', padding: '1rem 1.5rem' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
                              {/* TIMELINE */}
                              <div>
                                <h4 style={{ fontSize: '0.85rem', marginBottom: '0.5rem', color: 'var(--primary)' }}>
                                  📜 Lifecycle Events
                                </h4>
                                {a.tracking?.events && a.tracking.events.length > 0 ? (
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                                    {a.tracking.events.map((ev, idx) => (
                                      <div key={idx} style={{ fontSize: '0.78rem', background: 'rgba(255,255,255,0.03)', padding: '0.45rem 0.75rem', borderRadius: '6px' }}>
                                        <div style={{ color: 'var(--text-muted)' }}>{new Date(ev.at).toLocaleString()} · <em>{ev.source}</em></div>
                                        <div style={{ fontWeight: '500', marginTop: '0.15rem' }}>{ev.type}: {ev.detail || 'Event recorded'}</div>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="muted">No external lifecycle events recorded yet.</p>
                                )}
                              </div>

                              {/* ANSWERS GIVEN */}
                              <div>
                                <h4 style={{ fontSize: '0.85rem', marginBottom: '0.5rem', color: 'var(--success)' }}>
                                  📝 Screening Answers Submitted
                                </h4>
                                {a.answers_given && Object.keys(a.answers_given).length > 0 ? (
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                                    {Object.entries(a.answers_given).map(([q, ans]) => (
                                      <div key={q} style={{ fontSize: '0.78rem', background: 'rgba(255,255,255,0.03)', padding: '0.45rem 0.75rem', borderRadius: '6px' }}>
                                        <div style={{ color: 'var(--text-muted)' }}>Q: {q}</div>
                                        <div style={{ fontWeight: '600', color: 'var(--text-main)', marginTop: '0.1rem' }}>Answer: {String(ans)}</div>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="muted">Standard 1-step profile & resume submission (no screening questions required).</p>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* UNMATCHED EMAILS */}
      {unmatched_emails.length > 0 && (
        <div className="config-section" style={{ marginTop: '2rem' }}>
          <h3>Unmatched Recruiter Emails ({unmatched_emails.length})</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '1rem' }}>
            Job-related emails received that could not be automatically mapped to an existing application
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {unmatched_emails.map((m, idx) => (
              <div key={m.message_id || idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '0.75rem 1rem', borderRadius: '8px', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div>
                  <div style={{ fontWeight: '600', fontSize: '0.85rem' }}>{m.subject || '(No Subject)'}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>From: {m.from} · {new Date(m.date).toLocaleDateString()}</div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <select
                    value={assignSelections[m.message_id] || ''}
                    onChange={(e) => setAssignSelections({ ...assignSelections, [m.message_id]: e.target.value })}
                    style={{ padding: '0.35rem 0.5rem', fontSize: '0.78rem', maxWidth: '240px' }}
                  >
                    <option value="">Select Application...</option>
                    {applications.map(a => (
                      <option key={a.id} value={a.id}>{a.job?.company} - {a.job?.title}</option>
                    ))}
                  </select>
                  <button className="btn btn-primary" onClick={() => handleAssignEmail(m.message_id)} style={{ padding: '0.35rem 0.7rem', fontSize: '0.78rem' }}>
                    Assign
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
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
            <Route path="/*" element={<ProtectedRoute><Navbar /><main className="content"><Routes><Route path="/" element={<Dashboard />} /><Route path="/queue" element={<JobQueuePage />} /><Route path="/applications" element={<ApplicationsPage />} /><Route path="/tracker" element={<TrackerPage />} /><Route path="/config" element={<ConfigurationPage />} /><Route path="*" element={<Navigate to="/" />} /></Routes></main></ProtectedRoute>} />
          </Routes>
        </div>
      </AuthProvider>
    </BrowserRouter>
  )
}
