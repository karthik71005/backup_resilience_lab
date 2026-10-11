import React, { useState, useEffect, useRef, useCallback } from 'react';

// API base URL - defaults to empty string so requests go through Vite proxy or same-origin backend
const API_BASE = import.meta.env.VITE_API_URL || '';

// Clean SVG Icons
const Icons = {
  Shield: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  ),
  CheckCircle: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  ),
  AlertTriangle: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  XCircle: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="15" y1="9" x2="9" y2="15" />
      <line x1="9" y1="9" x2="15" y2="15" />
    </svg>
  ),
  Refresh: ({ spinning }) => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ animation: spinning ? 'spin 1s linear infinite' : 'none' }}>
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  ),
  Upload: () => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  ),
  Activity: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  ),
  Terminal: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  ),
  Copy: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  ),
  Check: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  Server: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
      <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
      <line x1="6" y1="6" x2="6.01" y2="6" />
      <line x1="6" y1="18" x2="6.01" y2="18" />
    </svg>
  ),
  Database: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  ),
  Flame: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z" />
    </svg>
  )
};

export default function App() {
  // Navigation
  const [activeTab, setActiveTab] = useState('overview');

  // Health state
  const [health, setHealth] = useState({
    global_status: 'checking',
    last_check: null,
    last_success: null,
    services: {},
    summary: { total: 0, healthy: 0, unhealthy: 0, degraded: 0 }
  });
  const [backendConnected, setBackendConnected] = useState(false);
  const [lastConnectionError, setLastConnectionError] = useState(null);
  const [isChecking, setIsChecking] = useState(false);

  // Overview metrics & detector
  const [overview, setOverview] = useState(null);
  const [detectorStatus, setDetectorStatus] = useState(null);

  // Protected files
  const [protectedFiles, setProtectedFiles] = useState({});
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileFingerprint, setFileFingerprint] = useState('');
  const [protectingFile, setProtectingFile] = useState(false);
  const [protectResult, setProtectResult] = useState(null);

  // Attack simulation
  const [attackRunning, setAttackRunning] = useState(false);
  const [attackResult, setAttackResult] = useState(null);

  // Restore & verify
  const [restoreRunning, setRestoreRunning] = useState(false);
  const [restoreResult, setRestoreResult] = useState(null);

  // Timeline
  const [timeline, setTimeline] = useState([]);
  const [timelineFilter, setTimelineFilter] = useState('all');

  // Diagnostics
  const [diagnosticsRunning, setDiagnosticsRunning] = useState(false);
  const [diagnosticsResult, setDiagnosticsResult] = useState(null);
  const [diagHistory, setDiagHistory] = useState([]);

  // Vault & Faults
  const [vaultData, setVaultData] = useState(null);
  const [faultSelected, setFaultSelected] = useState('permission_denied');
  const [faultOutput, setFaultOutput] = useState(null);
  const [triageOutput, setTriageOutput] = useState(null);

  // Service Restart Modal
  const [serviceToRestart, setServiceToRestart] = useState(null);
  const [restartingService, setRestartingService] = useState(false);
  const [restartOutput, setRestartOutput] = useState(null);

  // Copy notification helper
  const [copiedKey, setCopiedKey] = useState(null);

  // Polling lock ref to prevent overlapping requests
  const pollingRef = useRef(false);

  // Copy helper
  const copyToClipboard = (text, key) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // Compute client-side SHA-256 for instant feedback
  const computeFileHash = async (file) => {
    try {
      const buffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
      setFileFingerprint(hashHex);
    } catch {
      setFileFingerprint('Error computing local hash');
    }
  };

  // Health fetcher
  const fetchHealth = useCallback(async (force = false) => {
    if (pollingRef.current && !force) return;
    pollingRef.current = true;
    setIsChecking(true);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 6000);

      const endpoint = force ? `${API_BASE}/api/health/check` : `${API_BASE}/api/health`;
      const method = force ? 'POST' : 'GET';

      const res = await fetch(endpoint, {
        method,
        signal: controller.signal,
        headers: { 'Accept': 'application/json' }
      });
      clearTimeout(timeoutId);

      if (!res.ok) {
        throw new Error(`API returned HTTP ${res.status}`);
      }

      const data = await res.json();
      setHealth(data);
      setBackendConnected(true);
      setLastConnectionError(null);
    } catch (err) {
      setBackendConnected(false);
      setLastConnectionError(err.name === 'AbortError' ? 'Request timed out (6s)' : err.message);
      setHealth(prev => ({
        ...prev,
        global_status: 'offline'
      }));
    } finally {
      setIsChecking(false);
      pollingRef.current = false;
    }
  }, []);

  // Fetch overview & secondary data
  const fetchAuxData = useCallback(async () => {
    if (!backendConnected) return;

    try {
      // Fetch overview metrics
      const ovRes = await fetch(`${API_BASE}/api/overview`);
      if (ovRes.ok) {
        const ovData = await ovRes.json();
        setOverview(ovData.overview);
      }

      // Fetch detector status
      const detRes = await fetch(`${API_BASE}/api/detector/status`);
      if (detRes.ok) {
        const detData = await detRes.json();
        setDetectorStatus(detData.detector);
      }

      // Fetch timeline
      const tlRes = await fetch(`${API_BASE}/api/timeline`);
      if (tlRes.ok) {
        const tlData = await tlRes.json();
        setTimeline(tlData.events || []);
      }

      // Fetch protected files
      const pfRes = await fetch(`${API_BASE}/api/protected-files`);
      if (pfRes.ok) {
        const pfData = await pfRes.json();
        setProtectedFiles(pfData.files || {});
      }
    } catch (e) {
      // Handled silently during periodic polling
    }
  }, [backendConnected]);

  // Periodic polling every 5s
  useEffect(() => {
    fetchHealth();
    const interval = setInterval(() => {
      fetchHealth();
      fetchAuxData();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchHealth, fetchAuxData]);

  // Manual check system
  const handleCheckSystem = () => {
    fetchHealth(true);
    fetchAuxData();
  };

  // Run diagnostics
  const handleRunDiagnostics = async () => {
    setDiagnosticsRunning(true);
    try {
      const res = await fetch(`${API_BASE}/api/diagnostics`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setDiagnosticsResult(data);
        // Refresh history
        const histRes = await fetch(`${API_BASE}/api/diagnostics/history`);
        if (histRes.ok) {
          const histData = await histRes.json();
          setDiagHistory(histData.history || []);
        }
      }
    } catch (e) {
      alert('Failed to run diagnostics: ' + e.message);
    } finally {
      setDiagnosticsRunning(false);
      fetchAuxData();
    }
  };

  // File upload and protect workflow
  const handleFileUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    setProtectingFile(true);
    setProtectResult(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);

      // 1. Upload to victim directory
      const upRes = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        body: formData
      });
      const upData = await upRes.json();
      if (!upRes.ok) {
        throw new Error(upData.detail || 'Upload failed');
      }

      // 2. Protect (backup + snapshot verification)
      const protRes = await fetch(`${API_BASE}/api/protect`, { method: 'POST' });
      const protData = await protRes.json();

      setProtectResult({
        upload: upData,
        protection: protData,
        success: protRes.ok && protData.ok
      });

      // Clear input and reload files
      setSelectedFile(null);
      fetchAuxData();
    } catch (err) {
      setProtectResult({
        success: false,
        error: err.message
      });
    } finally {
      setProtectingFile(false);
    }
  };

  // Simulate Attack
  const handleSimulateAttack = async () => {
    if (!window.confirm('Simulate ransomware encryption on /data/victim in the isolated lab?')) return;
    setAttackRunning(true);
    setAttackResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/attack`, { method: 'POST' });
      const data = await res.json();
      setAttackResult(data);
      fetchAuxData();
      fetchHealth();
    } catch (err) {
      setAttackResult({ ok: false, error: err.message });
    } finally {
      setAttackRunning(false);
    }
  };

  // Restore Clean Backup
  const handleRestore = async () => {
    if (!window.confirm('Restore /data/victim from the latest verified clean snapshot?')) return;
    setRestoreRunning(true);
    setRestoreResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/restore`, { method: 'POST' });
      const data = await res.json();
      setRestoreResult(data);
      fetchAuxData();
      fetchHealth();
    } catch (err) {
      setRestoreResult({ ok: false, error: err.message });
    } finally {
      setRestoreRunning(false);
    }
  };

  // Resume Backups
  const handleResumeBackups = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/resume`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        alert('Backups resumed successfully');
      } else {
        alert('Failed to resume: ' + data.output);
      }
      fetchAuxData();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  };

  // Service Restart Action
  const handleConfirmRestart = async () => {
    if (!serviceToRestart) return;
    setRestartingService(true);
    setRestartOutput(null);

    try {
      const res = await fetch(`${API_BASE}/api/services/${serviceToRestart}/restart`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'restart', confirm: true })
      });
      const data = await res.json();
      setRestartOutput(data);
      fetchHealth(true);
    } catch (err) {
      setRestartOutput({ ok: false, output: err.message });
    } finally {
      setRestartingService(false);
    }
  };

  // Vault data
  const handleFetchVault = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/vault`);
      if (res.ok) {
        const data = await res.json();
        setVaultData(data);
      }
    } catch (e) {
      alert('Failed to query vault: ' + e.message);
    }
  };

  // Fault injection
  const handleInjectFault = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/fault`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: faultSelected })
      });
      const data = await res.json();
      setFaultOutput(data);
      fetchHealth(true);
    } catch (e) {
      setFaultOutput({ ok: false, error: e.message });
    }
  };

  // Clear faults
  const handleClearFaults = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/clear`, { method: 'POST' });
      const data = await res.json();
      setFaultOutput({ cleared: true, ...data });
      fetchHealth(true);
    } catch (e) {
      setFaultOutput({ ok: false, error: e.message });
    }
  };

  // Triage analyze
  const handleRunTriage = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/triage`, { method: 'POST' });
      const data = await res.json();
      setTriageOutput(data);
    } catch (e) {
      setTriageOutput({ ok: false, error: e.message });
    }
  };

  // Filtered timeline
  const filteredEvents = timeline.filter(ev => {
    if (timelineFilter === 'all') return true;
    return ev.type === timelineFilter;
  });

  // Global status colors
  const statusColors = {
    healthy: 'var(--color-success)',
    degraded: 'var(--color-warning)',
    offline: 'var(--color-danger)',
    checking: 'var(--color-info)',
    unknown: 'var(--text-dim)'
  };
  const currentStatus = health.global_status || 'unknown';

  return (
    <div className="app-container">
      {/* GLOBAL HEALTH BANNER */}
      <header className="global-banner" style={{ '--status-color': statusColors[currentStatus] }}>
        <div className="banner-title-area">
          <div style={{ color: 'var(--color-primary)', display: 'flex', alignItems: 'center' }}>
            <Icons.Shield />
          </div>
          <div>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
              BACKUP RESILIENCE LAB
            </h1>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
              RustFS S3 &bull; Restic Engine &bull; Entropy Watchdog &bull; SHA-256 Vault
            </p>
          </div>

          {/* Prominent Global Status Badge */}
          <div className={`status-indicator-badge status-badge-${currentStatus}`}>
            <span className="pulse-dot"></span>
            <span>SYSTEM {currentStatus.toUpperCase()}</span>
          </div>
        </div>

        <div className="banner-stats">
          <div className="stat-item">
            <span className="stat-label">API Connection</span>
            <span className="stat-value" style={{ color: backendConnected ? 'var(--color-success)' : 'var(--color-danger)' }}>
              {backendConnected ? 'Connected (Port 8090)' : 'Unreachable'}
            </span>
          </div>

          <div className="stat-item">
            <span className="stat-label">Services</span>
            <span className="stat-value">
              <span style={{ color: 'var(--color-success)' }}>{health.summary?.healthy ?? 0} UP</span>
              {' / '}
              <span style={{ color: (health.summary?.unhealthy ?? 0) > 0 ? 'var(--color-danger)' : 'var(--text-dim)' }}>
                {health.summary?.unhealthy ?? 0} DOWN
              </span>
            </span>
          </div>

          <div className="stat-item">
            <span className="stat-label">Last Checked</span>
            <span className="stat-value font-mono" style={{ fontSize: '0.8rem' }}>
              {health.last_check ? new Date(health.last_check).toLocaleTimeString() : 'Never'}
            </span>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={handleCheckSystem}
              disabled={isChecking}
              title="Force fresh health check"
            >
              <Icons.Refresh spinning={isChecking} />
              <span>{isChecking ? 'Checking...' : 'Check System'}</span>
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleRunDiagnostics}
              disabled={diagnosticsRunning}
            >
              <Icons.Activity />
              <span>{diagnosticsRunning ? 'Diagnosing...' : 'Diagnose'}</span>
            </button>
          </div>
        </div>
      </header>

      {/* BACKEND OFFLINE ALERT BOX */}
      {!backendConnected && (
        <div className="offline-alert-box">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--color-danger)' }}>
            <Icons.AlertTriangle />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>
              Backend API Is Unreachable ({lastConnectionError || 'Connection Refused'})
            </h3>
          </div>
          <p style={{ fontSize: '0.875rem', color: '#cbd5e1' }}>
            The frontend cannot communicate with the FastAPI backend on port 8090.
            The rest of the dashboard remains operational in offline mode. Last successful check was at{' '}
            <strong>{health.last_success ? new Date(health.last_success).toLocaleTimeString() : 'Never'}</strong>.
          </p>
          <div style={{ background: '#090d16', padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid #334155' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontWeight: 600 }}>
                SAFE WSL / TERMINAL RECOVERY COMMANDS
              </span>
              <button
                className="copy-btn"
                onClick={() => copyToClipboard('cd ~/projects/backup-resilience-lab && python dashboard/api.py', 'cmd-start')}
              >
                {copiedKey === 'cmd-start' ? <Icons.Check /> : <Icons.Copy />}
                <span>{copiedKey === 'cmd-start' ? 'Copied' : 'Copy Start Cmd'}</span>
              </button>
            </div>
            <pre className="font-mono" style={{ fontSize: '0.8rem', color: '#93c5fd' }}>
              # 1. Start the FastAPI backend:{'\n'}
              python dashboard/api.py --port 8090{'\n\n'}
              # 2. Or check Docker Compose containers:{'\n'}
              docker compose ps
            </pre>
          </div>
          <div>
            <button className="btn btn-primary btn-sm" onClick={() => fetchHealth(true)}>
              <Icons.Refresh spinning={isChecking} />
              <span>Retry Connection</span>
            </button>
          </div>
        </div>
      )}

      {/* WORKFLOW PIPELINE PROGRESS */}
      <div className="workflow-progress">
        <div className={`step-node ${backendConnected ? 'completed' : 'active'}`}>
          <div className="step-circle">{backendConnected ? '✓' : '1'}</div>
          <span>1. System Health</span>
        </div>
        <div className="step-divider" />
        <div className={`step-node ${Object.keys(protectedFiles).length > 0 ? 'completed' : 'active'}`}>
          <div className="step-circle">{Object.keys(protectedFiles).length > 0 ? '✓' : '2'}</div>
          <span>2. Protect File</span>
        </div>
        <div className="step-divider" />
        <div className={`step-node ${(overview?.clean || 0) > 0 ? 'completed' : ''}`}>
          <div className="step-circle">{(overview?.clean || 0) > 0 ? '✓' : '3'}</div>
          <span>3. Verified Backup</span>
        </div>
        <div className="step-divider" />
        <div className={`step-node ${detectorStatus?.is_alerting ? 'completed' : ''}`}>
          <div className="step-circle">{detectorStatus?.is_alerting ? '!' : '4'}</div>
          <span>4. Detect Attack</span>
        </div>
        <div className="step-divider" />
        <div className={`step-node ${restoreResult?.ok ? 'completed' : ''}`}>
          <div className="step-circle">{restoreResult?.ok ? '✓' : '5'}</div>
          <span>5. Verified Recovery</span>
        </div>
      </div>

      {/* NAVIGATION TABS */}
      <nav className="tab-navigation">
        {[
          { id: 'overview', label: '1. Overview & Health', icon: Icons.Server },
          { id: 'protect', label: '2. Protect a File', icon: Icons.Upload },
          { id: 'monitoring', label: '3. Monitoring & Detector', icon: Icons.Activity },
          { id: 'attack', label: '4. Attack Simulation', icon: Icons.Flame },
          { id: 'recovery', label: '5. Recovery & Verify', icon: Icons.CheckCircle },
          { id: 'diagnostics', label: '6. Diagnostics & Debug', icon: Icons.Terminal },
          { id: 'timeline', label: '7. Activity Timeline', icon: Icons.Activity },
          { id: 'faults', label: '8. Fault Lab & Triage', icon: Icons.AlertTriangle }
        ].map(tab => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              className={`nav-tab-button ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>

      {/* TAB CONTENT */}

      {/* 1. OVERVIEW & HEALTH */}
      {activeTab === 'overview' && (
        <div className="sections-grid">
          {/* Key metrics cards */}
          <div className="col-12" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            <div className="lab-card" style={{ padding: '1.25rem' }}>
              <span className="stat-label">Detector Score</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
                <span style={{ fontSize: '1.8rem', fontWeight: 800, color: (detectorStatus?.score || 0) >= 0.55 ? 'var(--color-danger)' : 'var(--color-success)' }}>
                  {detectorStatus?.score !== null && detectorStatus?.score !== undefined ? detectorStatus.score.toFixed(3) : '0.000'}
                </span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>/ threshold 0.55</span>
              </div>
              <span style={{ fontSize: '0.75rem', color: detectorStatus?.is_alerting ? 'var(--color-danger)' : 'var(--text-dim)' }}>
                {detectorStatus?.is_alerting ? 'ALERT ACTIVE' : 'Normal file entropy'}
              </span>
            </div>

            <div className="lab-card" style={{ padding: '1.25rem' }}>
              <span className="stat-label">Clean Snapshots</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--color-success)' }}>
                {overview?.clean ?? 0}
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Eligible for fast restore</span>
            </div>

            <div className="lab-card" style={{ padding: '1.25rem' }}>
              <span className="stat-label">Suspect Snapshots</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: (overview?.suspect ?? 0) > 0 ? 'var(--color-warning)' : 'var(--text-dim)' }}>
                {overview?.suspect ?? 0}
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Quarantined snapshots</span>
            </div>

            <div className="lab-card" style={{ padding: '1.25rem' }}>
              <span className="stat-label">Backup Schedule</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: detectorStatus?.paused ? 'var(--color-warning)' : 'var(--color-success)' }}>
                {detectorStatus?.paused ? 'PAUSED' : 'ACTIVE'}
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                {detectorStatus?.paused ? 'Backups halted on alert' : 'Continuous protection'}
              </span>
            </div>

            <div className="lab-card" style={{ padding: '1.25rem' }}>
              <span className="stat-label">Victim File Count</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--color-primary)' }}>
                {overview?.victim_entries !== undefined && overview?.victim_entries >= 0 ? overview.victim_entries : 'N/A'}
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Items in /data/victim</span>
            </div>
          </div>

          {/* Services Table */}
          <div className="col-12 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Server /> Component Health Matrix</h2>
                <p className="card-subtitle">Real status checks against RustFS, App Servers, Vault, and Monitoring</p>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={handleCheckSystem} disabled={isChecking}>
                <Icons.Refresh spinning={isChecking} />
                <span>Recheck All</span>
              </button>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table className="services-table">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Status</th>
                    <th>Latency</th>
                    <th>Type</th>
                    <th>Diagnostics / Details</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(health.services || {}).map(([key, s]) => {
                    const statusClass = s.status === 'healthy' ? 'badge-healthy' : s.status === 'degraded' ? 'badge-warn' : 'badge-unhealthy';
                    return (
                      <tr key={key}>
                        <td style={{ fontWeight: 600 }}>{s.name || key}</td>
                        <td>
                          <span className={`service-badge ${statusClass}`}>
                            {s.status.toUpperCase()}
                          </span>
                        </td>
                        <td className="font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                          {s.latency_ms ? `${s.latency_ms.toFixed(0)} ms` : '—'}
                        </td>
                        <td style={{ fontSize: '0.8rem', color: 'var(--text-dim)', textTransform: 'capitalize' }}>
                          {s.check_type || 'direct'}
                        </td>
                        <td style={{ fontSize: '0.8rem', color: s.error ? 'var(--color-danger)' : 'var(--text-muted)' }}>
                          {s.error || s.details || 'Responding nominally'}
                          {s.blocks && (
                            <div style={{ color: 'var(--color-warning)', fontSize: '0.75rem', marginTop: '0.2rem' }}>
                              Blocks: {s.blocks}
                            </div>
                          )}
                        </td>
                        <td>
                          {['minio', 'app-server-1', 'app-server-2', 'prometheus', 'grafana'].includes(key) && (
                            <button
                              className="btn btn-secondary btn-sm"
                              style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}
                              onClick={() => {
                                setServiceToRestart(key);
                                setRestartOutput(null);
                              }}
                            >
                              Restart
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {Object.keys(health.services || {}).length === 0 && (
                    <tr>
                      <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '2rem' }}>
                        {backendConnected ? 'No services reported. Click "Check System".' : 'Backend offline. Services status unavailable.'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* 2. PROTECT A FILE */}
      {activeTab === 'protect' && (
        <div className="sections-grid">
          <div className="col-6 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Upload /> Upload &amp; Protect File</h2>
                <p className="card-subtitle">Secure upload to /data/victim with instant SHA-256 fingerprinting</p>
              </div>
            </div>

            <form onSubmit={handleFileUpload} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div
                className="upload-dropzone"
                onClick={() => document.getElementById('file-input')?.click()}
              >
                <input
                  id="file-input"
                  type="file"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      setSelectedFile(file);
                      computeFileHash(file);
                    }
                  }}
                />
                <div className="upload-icon"><Icons.Upload /></div>
                <div style={{ fontWeight: 600, fontSize: '0.95rem', marginBottom: '0.25rem' }}>
                  {selectedFile ? selectedFile.name : 'Choose or drop a disposable test file'}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  {selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB` : 'Max 50MB. Staged safely in lab victim volume.'}
                </div>
              </div>

              {selectedFile && (
                <div style={{ background: 'var(--bg-subtle)', padding: '0.85rem', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.25rem' }}>
                    CLIENT SHA-256 FINGERPRINT
                  </div>
                  <div className="font-mono" style={{ fontSize: '0.75rem', color: 'var(--color-primary)', wordBreak: 'break-all' }}>
                    {fileFingerprint || 'Calculating...'}
                  </div>
                </div>
              )}

              <button
                type="submit"
                className="btn btn-primary"
                disabled={!selectedFile || protectingFile || !backendConnected}
              >
                <Icons.Shield />
                <span>{protectingFile ? 'Protecting (Upload + Backup)...' : 'Upload & Create Verified Backup'}</span>
              </button>
            </form>

            {protectResult && (
              <div style={{ marginTop: '0.5rem' }}>
                {protectResult.success ? (
                  <div style={{ background: 'var(--color-success-bg)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: 'var(--radius-sm)', padding: '0.85rem' }}>
                    <div style={{ color: 'var(--color-success)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <Icons.CheckCircle /> File Successfully Protected!
                    </div>
                    <div style={{ fontSize: '0.8rem', marginTop: '0.35rem', color: '#cbd5e1' }}>
                      Snapshot ID: <span className="font-mono" style={{ color: '#93c5fd' }}>{protectResult.protection?.snapshot_id || 'Recorded'}</span>
                    </div>
                  </div>
                ) : (
                  <div style={{ background: 'var(--color-danger-bg)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 'var(--radius-sm)', padding: '0.85rem' }}>
                    <div style={{ color: 'var(--color-danger)', fontWeight: 700 }}>
                      Protection Failed
                    </div>
                    <div style={{ fontSize: '0.8rem', marginTop: '0.35rem', color: '#cbd5e1' }}>
                      {protectResult.error || protectResult.protection?.output}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="col-6 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Database /> Tracked Protected Files</h2>
                <p className="card-subtitle">Recorded fingerprints in the clean snapshot catalogue</p>
              </div>
            </div>

            <div style={{ overflowY: 'auto', maxHeight: '420px' }}>
              {Object.entries(protectedFiles).length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {Object.entries(protectedFiles).map(([fname, f]) => (
                    <div key={fname} style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '0.85rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>{f.name}</span>
                        <span className={`service-badge ${f.protected ? 'badge-healthy' : 'badge-warn'}`}>
                          {f.protected ? 'PROTECTED' : 'STAGED'}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.25rem' }}>
                        Size: {(f.size / 1024).toFixed(1)} KB &bull; Uploaded: {new Date(f.uploaded_at).toLocaleTimeString()}
                      </div>
                      <div className="font-mono" style={{ fontSize: '0.7rem', color: 'var(--text-muted)', wordBreak: 'break-all' }}>
                        SHA-256: {f.fingerprint}
                      </div>
                      {f.backup_snapshot && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-info)', marginTop: '0.35rem' }}>
                          Snapshot: <span className="font-mono">{f.backup_snapshot.substring(0, 8)}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '3rem 1rem' }}>
                  No protected files tracked in this session yet. Upload a sample file to begin.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 3. MONITORING & DETECTOR */}
      {activeTab === 'monitoring' && (
        <div className="sections-grid">
          <div className="col-6 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Activity /> Filesystem Watchdog Detector</h2>
                <p className="card-subtitle">Real-time entropy and rename velocity monitoring on /data/victim</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>Suspicion Score Gauge</span>
                  <span className="font-mono" style={{ fontWeight: 700, color: (detectorStatus?.score || 0) >= 0.55 ? 'var(--color-danger)' : 'var(--color-success)' }}>
                    {detectorStatus?.score !== null && detectorStatus?.score !== undefined ? detectorStatus.score.toFixed(3) : '0.000'} / 0.550
                  </span>
                </div>
                <div style={{ height: '14px', background: 'var(--bg-subtle)', borderRadius: '9999px', overflow: 'hidden', position: 'relative' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.min(100, ((detectorStatus?.score || 0) / 0.55) * 100)}%`,
                      background: (detectorStatus?.score || 0) >= 0.55 ? 'var(--color-danger)' : 'var(--color-success)',
                      transition: 'width 0.4s ease'
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div style={{ background: 'var(--bg-subtle)', padding: '0.85rem', borderRadius: 'var(--radius-sm)' }}>
                  <span className="stat-label">Alert Status</span>
                  <div style={{ fontWeight: 700, fontSize: '1.1rem', color: detectorStatus?.is_alerting ? 'var(--color-danger)' : 'var(--color-success)' }}>
                    {detectorStatus?.is_alerting ? 'ALERT TRIGGERED' : 'CLEAR'}
                  </div>
                </div>

                <div style={{ background: 'var(--bg-subtle)', padding: '0.85rem', borderRadius: 'var(--radius-sm)' }}>
                  <span className="stat-label">Backup Circuit Breaker</span>
                  <div style={{ fontWeight: 700, fontSize: '1.1rem', color: detectorStatus?.paused ? 'var(--color-warning)' : 'var(--color-success)' }}>
                    {detectorStatus?.paused ? 'PAUSED' : 'ENGAGED'}
                  </div>
                </div>
              </div>

              {detectorStatus?.paused && (
                <div style={{ background: 'var(--color-warning-bg)', border: '1px solid rgba(245, 158, 11, 0.3)', padding: '0.85rem', borderRadius: 'var(--radius-sm)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.85rem', color: 'var(--color-warning)' }}>
                    Scheduled backups are paused to prevent corrupting the clean repository.
                  </span>
                  <button className="btn btn-warning btn-sm" onClick={handleResumeBackups}>
                    Resume Backups
                  </button>
                </div>
              )}

              <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', lineHeight: '1.5' }}>
                <strong>How it works:</strong> The detector runs inside <code>app-server-1</code>, observing inotify events via Python Watchdog. When mass file modifications or sudden entropy spikes exceed the threshold (0.55), the detector halts Restic scheduled backups and classifies subsequent snapshots as suspect in SQLite.
              </div>
            </div>
          </div>

          <div className="col-6 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Terminal /> Snapshot Classification State</h2>
                <p className="card-subtitle">SQLite catalog distinguishing verified clean vs quarantined suspect backups</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <span style={{ fontWeight: 600 }}>Total Alerts Recorded</span>
                <span className="font-mono" style={{ color: 'var(--color-danger)', fontWeight: 700 }}>
                  {overview?.alerts ? Object.values(overview.alerts).reduce((a, b) => Number(a) + Number(b), 0) : 0}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <span style={{ fontWeight: 600 }}>Clean Snapshots (Safe for Restore)</span>
                <span className="font-mono" style={{ color: 'var(--color-success)', fontWeight: 700 }}>
                  {overview?.clean ?? 0}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <span style={{ fontWeight: 600 }}>Suspect Snapshots (Quarantined)</span>
                <span className="font-mono" style={{ color: 'var(--color-warning)', fontWeight: 700 }}>
                  {overview?.suspect ?? 0}
                </span>
              </div>

              <div style={{ marginTop: '0.5rem' }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-dim)', display: 'block', marginBottom: '0.4rem' }}>
                  RECENT SNAPSHOT CATALOGUE
                </span>
                <div style={{ maxHeight: '200px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  {Array.isArray(overview?.snapshots) && overview.snapshots.length > 0 ? (
                    overview.snapshots.map((snap) => (
                      <div key={snap.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#090d16', padding: '0.5rem 0.75rem', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem' }}>
                        <span className="font-mono" style={{ color: 'var(--color-primary)' }}>{snap.id.substring(0, 8)}</span>
                        <span style={{ color: 'var(--text-dim)' }}>{snap.time ? new Date(snap.time).toLocaleTimeString() : 'N/A'}</span>
                        <span className={`service-badge ${snap.status === 'clean' ? 'badge-healthy' : 'badge-warn'}`}>
                          {snap.status || 'clean'}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', textAlign: 'center', padding: '1rem' }}>
                      No snapshots recorded yet.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 4. ATTACK SIMULATION */}
      {activeTab === 'attack' && (
        <div className="sections-grid">
          <div className="col-8 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Flame /> Guarded Ransomware Simulation</h2>
                <p className="card-subtitle">Runs real lab attack simulation (15 files/sec encryption) with strict safety guards</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ background: 'var(--bg-subtle)', padding: '1rem', borderRadius: 'var(--radius-sm)', borderLeft: '4px solid var(--color-warning)' }}>
                <h4 style={{ color: 'var(--color-warning)', marginBottom: '0.35rem', fontSize: '0.9rem' }}>
                  Safety Pre-Flight Conditions
                </h4>
                <ul style={{ fontSize: '0.8rem', color: '#cbd5e1', paddingLeft: '1.25rem', lineHeight: '1.6' }}>
                  <li>Restricted strictly to the isolated <code>/data/victim</code> volume inside Docker.</li>
                  <li>Pre-check: verified clean backup must exist before attack is permitted.</li>
                  <li>Preserves original immutable backups in RustFS S3 with GOVERNANCE lock.</li>
                  <li>Simulates high-velocity AES encryption to test the watchdog detector.</li>
                </ul>
              </div>

              <div>
                <button
                  className="btn btn-danger"
                  onClick={handleSimulateAttack}
                  disabled={attackRunning || !backendConnected}
                  style={{ width: '100%', padding: '0.85rem' }}
                >
                  <Icons.Flame />
                  <span>{attackRunning ? 'Executing Attack Simulation...' : 'Simulate Ransomware Attack'}</span>
                </button>
              </div>

              {attackResult && (
                <div style={{ marginTop: '0.5rem' }}>
                  <div style={{ background: attackResult.ok ? 'var(--color-danger-bg)' : 'var(--bg-subtle)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <span style={{ fontWeight: 700, color: attackResult.ok ? 'var(--color-danger)' : 'var(--text-main)' }}>
                        {attackResult.ok ? 'Attack Simulation Completed' : 'Simulation Refused / Failed'}
                      </span>
                      {attackResult.post_attack && (
                        <span className={`service-badge ${attackResult.post_attack.detected ? 'badge-fail' : 'badge-warn'}`}>
                          {attackResult.post_attack.detected ? 'DETECTOR TRIGGERED' : 'NOT DETECTED'}
                        </span>
                      )}
                    </div>
                    {attackResult.reason && (
                      <div style={{ color: 'var(--color-warning)', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                        Pre-check notice: {attackResult.reason}
                      </div>
                    )}
                    {attackResult.attack_result && (
                      <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '0.5rem' }}>
                        Encrypted files: <strong>{attackResult.attack_result.files || '300+'}</strong> &bull;
                        Post-attack score: <strong style={{ color: 'var(--color-danger)' }}>{attackResult.post_attack?.detector_score?.toFixed(3) || 'N/A'}</strong>
                      </div>
                    )}
                    <pre className="code-block">{attackResult.output || JSON.stringify(attackResult, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="col-4 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Activity /> Detection Feedback</h2>
                <p className="card-subtitle">Real-time detector reaction</p>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ background: 'var(--bg-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                <span className="stat-label">Alert Count</span>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--color-danger)' }}>
                  {overview?.alerts ? Object.values(overview.alerts).reduce((a, b) => Number(a) + Number(b), 0) : 0}
                </div>
              </div>
              <div style={{ background: 'var(--bg-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                <span className="stat-label">Backup Circuit Status</span>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: detectorStatus?.paused ? 'var(--color-warning)' : 'var(--color-success)' }}>
                  {detectorStatus?.paused ? 'HALTED (Safe)' : 'Normal'}
                </div>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', lineHeight: '1.5' }}>
                When ransomware encrypts files, entropy jumps to &gt;7.5 bits/byte. The lab halts backups to ensure suspect files are never backed up over clean copies.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 5. RECOVERY & VERIFY */}
      {activeTab === 'recovery' && (
        <div className="sections-grid">
          <div className="col-8 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.CheckCircle /> Restore &amp; Cryptographic Verification</h2>
                <p className="card-subtitle">Restores latest clean snapshot and validates SHA-256 integrity against the manifest</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                The lab recovers from the verified <code>clean</code> snapshot into a safe target directory, comparing every recovered file's SHA-256 hash against the pre-attack manifest.
              </p>

              <div>
                <button
                  className="btn btn-success"
                  onClick={handleRestore}
                  disabled={restoreRunning || !backendConnected}
                  style={{ width: '100%', padding: '0.85rem' }}
                >
                  <Icons.CheckCircle />
                  <span>{restoreRunning ? 'Restoring and Verifying Manifest...' : 'Restore Latest Clean Backup'}</span>
                </button>
              </div>

              {restoreResult && (
                <div style={{ marginTop: '0.5rem' }}>
                  <div style={{ background: restoreResult.ok ? 'var(--color-success-bg)' : 'var(--color-danger-bg)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <span style={{ fontWeight: 700, color: restoreResult.ok ? 'var(--color-success)' : 'var(--color-danger)' }}>
                        {restoreResult.ok ? 'Recovery and Verification Successful' : 'Restore Failed'}
                      </span>
                      {restoreResult.rto_seconds !== undefined && (
                        <span className="service-badge badge-healthy">
                          RTO: {restoreResult.rto_seconds}s
                        </span>
                      )}
                    </div>

                    {restoreResult.verification && (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', marginBottom: '0.75rem' }}>
                        <div style={{ background: 'var(--bg-subtle)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>TOTAL FILES</div>
                          <div style={{ fontWeight: 700, color: 'var(--text-main)' }}>{restoreResult.verification.total_files}</div>
                        </div>
                        <div style={{ background: 'var(--bg-subtle)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>VERIFIED OK</div>
                          <div style={{ fontWeight: 700, color: 'var(--color-success)' }}>{restoreResult.verification.verified_ok}</div>
                        </div>
                        <div style={{ background: 'var(--bg-subtle)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>SUCCESS RATE</div>
                          <div style={{ fontWeight: 700, color: 'var(--color-success)' }}>{restoreResult.verification.success_pct || 100}%</div>
                        </div>
                      </div>
                    )}

                    <pre className="code-block">{restoreResult.output || JSON.stringify(restoreResult, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="col-4 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Database /> Protected File Match</h2>
                <p className="card-subtitle">Original vs Restored Hashes</p>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {Object.entries(protectedFiles).map(([name, info]) => (
                <div key={name} style={{ background: 'var(--bg-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontWeight: 700, fontSize: '0.85rem' }}>{name}</div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>ORIGINAL SHA-256:</div>
                  <div className="font-mono" style={{ fontSize: '0.65rem', color: 'var(--color-primary)', wordBreak: 'break-all' }}>
                    {info.fingerprint}
                  </div>
                  <div style={{ marginTop: '0.35rem', fontSize: '0.75rem', color: info.verified ? 'var(--color-success)' : 'var(--text-dim)' }}>
                    {info.verified ? '✓ Recovered & Verified' : 'Awaiting restore run'}
                  </div>
                </div>
              ))}
              {Object.keys(protectedFiles).length === 0 && (
                <div style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '1.5rem' }}>
                  No uploaded sample files tracked yet.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 6. DIAGNOSTICS & DEBUG */}
      {activeTab === 'diagnostics' && (
        <div className="sections-grid">
          <div className="col-12 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Terminal /> Deep System Diagnostics</h2>
                <p className="card-subtitle">Structured, read-only multi-point inspection of all lab dependencies and logs</p>
              </div>
              <button className="btn btn-primary btn-sm" onClick={handleRunDiagnostics} disabled={diagnosticsRunning}>
                <Icons.Activity />
                <span>{diagnosticsRunning ? 'Running Checks...' : 'Run Diagnostics Now'}</span>
              </button>
            </div>

            {diagnosticsResult ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', gap: '1rem', background: 'var(--bg-subtle)', padding: '0.85rem 1.25rem', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: '0.85rem' }}>
                    Diagnostic Run: <strong className="font-mono">{diagnosticsResult.diagnostic_id}</strong>
                  </span>
                  <span style={{ fontSize: '0.85rem', color: 'var(--color-success)' }}>
                    Passed: <strong>{diagnosticsResult.summary?.passed}</strong>
                  </span>
                  <span style={{ fontSize: '0.85rem', color: (diagnosticsResult.summary?.failed || 0) > 0 ? 'var(--color-danger)' : 'var(--text-dim)' }}>
                    Failed: <strong>{diagnosticsResult.summary?.failed}</strong>
                  </span>
                </div>

                <div style={{ overflowX: 'auto' }}>
                  <table className="services-table">
                    <thead>
                      <tr>
                        <th>Component</th>
                        <th>Check Performed</th>
                        <th>Status</th>
                        <th>Observed</th>
                        <th>Likely Cause / Recommended Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diagnosticsResult.checks?.map((c) => (
                        <tr key={c.id}>
                          <td style={{ fontWeight: 600 }}>{c.component}</td>
                          <td>{c.check}</td>
                          <td>
                            <span className={`service-badge ${c.status === 'pass' ? 'badge-healthy' : c.status === 'fail' ? 'badge-unhealthy' : 'badge-warn'}`}>
                              {c.status.toUpperCase()}
                            </span>
                          </td>
                          <td className="font-mono" style={{ fontSize: '0.75rem', color: '#cbd5e1' }}>{c.observed}</td>
                          <td style={{ fontSize: '0.8rem' }}>
                            {c.likely_cause && <div style={{ color: 'var(--color-warning)' }}>Cause: {c.likely_cause}</div>}
                            {c.recommended_action && <div style={{ color: 'var(--color-primary)' }}>Action: {c.recommended_action}</div>}
                            {!c.likely_cause && !c.recommended_action && <span style={{ color: 'var(--text-dim)' }}>Nominal</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                Click "Run Diagnostics Now" to perform a real diagnostic evaluation.
              </div>
            )}
          </div>
        </div>
      )}

      {/* 7. ACTIVITY TIMELINE */}
      {activeTab === 'timeline' && (
        <div className="sections-grid">
          <div className="col-12 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Activity /> Real Activity Timeline</h2>
                <p className="card-subtitle">Chronological record of lab events from the FastAPI event broker</p>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                {['all', 'upload', 'backup', 'attack', 'restore', 'fault', 'service_action'].map((f) => (
                  <button
                    key={f}
                    className={`btn btn-secondary btn-sm ${timelineFilter === f ? 'btn-primary' : ''}`}
                    onClick={() => setTimelineFilter(f)}
                    style={{ textTransform: 'capitalize' }}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>

            <div className="timeline-list">
              {filteredEvents.map((ev) => (
                <div key={ev.id} className={`timeline-item status-${ev.status || 'info'}`}>
                  <div className="timeline-time">
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </div>
                  <div className="timeline-content">
                    <div className="timeline-title">
                      <span style={{ textTransform: 'uppercase', fontSize: '0.7rem', color: 'var(--text-dim)', marginRight: '0.5rem', background: 'var(--bg-dark)', padding: '0.15rem 0.4rem', borderRadius: '3px' }}>
                        {ev.type}
                      </span>
                      {ev.message}
                    </div>
                    {ev.details && Object.keys(ev.details).length > 0 && (
                      <div className="timeline-meta">
                        {JSON.stringify(ev.details)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {filteredEvents.length === 0 && (
                <div style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '3rem' }}>
                  No timeline events recorded yet.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 8. FAULT LAB & TRIAGE */}
      {activeTab === 'faults' && (
        <div className="sections-grid">
          <div className="col-6 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.AlertTriangle /> Fault Injection Suite</h2>
                <p className="card-subtitle">Test resilience against real failure modes (allowlisted)</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-dim)', display: 'block', marginBottom: '0.4rem' }}>
                  SELECT FAULT SCENARIO
                </label>
                <select
                  value={faultSelected}
                  onChange={(e) => setFaultSelected(e.target.value)}
                  style={{ width: '100%', background: 'var(--bg-subtle)', border: '1px solid var(--border-color)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: 'var(--radius-sm)' }}
                >
                  <option value="permission_denied">permission_denied (Read-only victim files)</option>
                  <option value="dns_failure">dns_failure (Network disconnect)</option>
                  <option value="service_down">service_down (Stop RustFS MinIO)</option>
                  <option value="bad_credentials">bad_credentials (Invalid AWS access keys)</option>
                  <option value="wrong_repo_password">wrong_repo_password (Restic password mismatch)</option>
                  <option value="disk_full">disk_full (Simulated volume quota)</option>
                  <option value="port_blocked">port_blocked (S3 port 9000 iptables drop)</option>
                </select>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button className="btn btn-warning" onClick={handleInjectFault} style={{ flex: 1 }}>
                  Inject Fault
                </button>
                <button className="btn btn-success" onClick={handleClearFaults} style={{ flex: 1 }}>
                  Clear Faults
                </button>
              </div>

              {faultOutput && (
                <div style={{ marginTop: '0.5rem' }}>
                  <pre className="code-block">{JSON.stringify(faultOutput, null, 2)}</pre>
                </div>
              )}
            </div>
          </div>

          <div className="col-6 lab-card">
            <div className="card-header">
              <div>
                <h2 className="card-title"><Icons.Terminal /> Automated Failure Triage</h2>
                <p className="card-subtitle">Analyzes recent failure logs with lab.triage expert rules</p>
              </div>
              <button className="btn btn-primary btn-sm" onClick={handleRunTriage}>
                Analyze Logs
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {triageOutput ? (
                <div>
                  <div style={{ fontSize: '0.85rem', marginBottom: '0.5rem', color: '#cbd5e1' }}>
                    Failures Analyzed: <strong>{triageOutput.failures ?? 0}</strong>
                  </div>
                  <pre className="code-block">{JSON.stringify(triageOutput.groups || triageOutput, null, 2)}</pre>
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-dim)' }}>
                  Click "Analyze Logs" to inspect recent backup failure logs and get suggested fixes.
                </div>
              )}

              <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Vault Governance Retention</span>
                  <button className="btn btn-secondary btn-sm" onClick={handleFetchVault}>
                    Query Vault
                  </button>
                </div>
                {vaultData && (
                  <pre className="code-block">{vaultData.status || vaultData.try_delete || JSON.stringify(vaultData, null, 2)}</pre>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SERVICE RESTART CONFIRMATION MODAL */}
      {serviceToRestart && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }}>
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)', padding: '1.75rem', maxWidth: '480px', width: '90%' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-warning)' }}>
              <Icons.AlertTriangle /> Confirm Service Restart
            </h3>
            <p style={{ fontSize: '0.875rem', color: '#cbd5e1', marginBottom: '1rem', lineHeight: '1.5' }}>
              Are you sure you want to restart container <strong>{serviceToRestart}</strong>? This runs <code>docker compose restart {serviceToRestart}</code> on the host.
            </p>

            {restartOutput && (
              <pre className="code-block" style={{ marginBottom: '1rem' }}>
                {restartOutput.output || (restartOutput.ok ? 'Restart succeeded' : 'Restart failed')}
              </pre>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setServiceToRestart(null)}
                disabled={restartingService}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleConfirmRestart}
                disabled={restartingService}
              >
                {restartingService ? 'Restarting...' : 'Confirm Restart'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
