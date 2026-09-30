import React, { useState, useEffect, useRef } from 'react';

const LiveFeed = ({ API }) => {
    const [logs, setLogs] = useState([]);
    const [isActive, setIsActive] = useState(false);
    const scrollRef = useRef(null);

    useEffect(() => {
        const fetchLogs = async () => {
            try {
                const data = await API.request('/api/logs');
                if (data && data.logs) {
                    setLogs(data.logs);
                    // Simple activation check: if logs have changed in the last 10s
                    setIsActive(data.logs.length > 0);
                }
            } catch (err) {
                console.error('Failed to fetch logs:', err);
            }
        };

        fetchLogs();
        const interval = setInterval(fetchLogs, 2000); // Poll every 2 seconds
        return () => clearInterval(interval);
    }, [API]);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);

    return (
        <div className="live-feed-container glass" style={{ height: '300px', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--card-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '0.9rem', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span className={`pulse-dot ${isActive ? 'active' : ''}`}></span>
                    Live Execution Feed
                </h3>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Real-time streaming</span>
            </div>
            <div
                ref={scrollRef}
                style={{
                    flex: 1,
                    padding: '1rem',
                    fontFamily: 'monospace',
                    fontSize: '0.8rem',
                    overflowY: 'auto',
                    background: 'rgba(0,0,0,0.2)',
                    color: '#e2e8f0'
                }}
            >
                {logs.length === 0 ? (
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Waiting for agent activity...</div>
                ) : (
                    logs.map((log, i) => (
                        <div key={i} style={{ marginBottom: '0.4rem', lineBreak: 'anywhere' }}>
                            <span style={{ color: 'var(--primary)', marginRight: '0.5rem' }}>[{log.time}]</span>
                            <span style={{ color: log.level === 'ERROR' ? 'var(--danger)' : log.level === 'WARNING' ? 'var(--warning)' : 'inherit' }}>
                                {log.message}
                            </span>
                        </div>
                    ))
                )}
            </div>
            <style>{`
        .pulse-dot {
          width: 8px;
          height: 8px;
          background: #475569;
          border-radius: 50%;
          transition: background 0.3s;
        }
        .pulse-dot.active {
          background: var(--success);
          box-shadow: 0 0 8px var(--success);
          animation: pulse 2s infinite;
        }
        @keyframes pulse {
          0% { opacity: 1; }
          50% { opacity: 0.4; }
          100% { opacity: 1; }
        }
      `}</style>
        </div>
    );
};

export default LiveFeed;
