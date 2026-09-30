import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [stats, setStats] = useState({
    applied_today: 0,
    total_applied: 0,
    success_rate: 0,
    active_jobs_in_queue: 0,
    system_status: 'loading...'
  });

  const [applications, setApplications] = useState([]);

  useEffect(() => {
    fetchStats();
    fetchApplications();
    const interval = setInterval(() => {
      fetchStats();
      fetchApplications();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchStats = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/stats');
      const data = await res.json();
      setStats(data);
    } catch (err) {
      console.error("Failed to fetch stats", err);
    }
  };

  const fetchApplications = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/applications');
      const data = await res.json();
      setApplications(data);
    } catch (err) {
      console.error("Failed to fetch applications", err);
    }
  };

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Job Application Agent</h1>
        <div className={`status-badge ${stats.system_status}`}>
          {stats.system_status.toUpperCase()}
        </div>
      </header>

      <main className="dashboard-content">
        <section className="stats-grid">
          <div className="stat-card">
            <h3>Applied Today</h3>
            <p className="stat-value">{stats.applied_today}</p>
          </div>
          <div className="stat-card">
            <h3>Total Applied</h3>
            <p className="stat-value">{stats.total_applied}</p>
          </div>
          <div className="stat-card">
            <h3>Success Rate</h3>
            <p className="stat-value">{stats.success_rate}%</p>
          </div>
          <div className="stat-card">
            <h3>Queue</h3>
            <p className="stat-value">{stats.active_jobs_in_queue}</p>
          </div>
        </section>

        <section className="activity-section">
          <h2>Recent Activity</h2>
          <div className="activity-list">
            {applications.length > 0 ? (
              applications.map((app, i) => (
                <div key={i} className="activity-item">
                  <div className="app-info">
                    <span className="app-company">{app.job.company}</span>
                    <span className="app-title">{app.job.title}</span>
                  </div>
                  <div className="app-meta">
                    <span className={`app-status ${app.status}`}>{app.status}</span>
                    <span className="app-time">{new Date(app.submission_timestamp).toLocaleString()}</span>
                  </div>
                </div>
              ))
            ) : (
              <p>No recent applications found.</p>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
