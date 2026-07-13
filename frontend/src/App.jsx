import React, { useState, useEffect, useRef } from 'react';

const INITIAL_STEPS = [
  { id: 'init', title: 'Initialization', details: 'Waiting to start...', status: 'idle' },
  { id: 'perms', title: 'Permutations Engine', details: 'Pending name input...', status: 'idle' },
  { id: 'dns', title: 'DNS Mail Server Lookup', details: 'Pending domain resolution...', status: 'idle' },
  { id: 'smtp', title: 'Verification checks', details: 'Pending handshake testing...', status: 'idle' }
];

function App() {
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState(INITIAL_STEPS);
  const [permutations, setPermutations] = useState([]);
  const [result, setResult] = useState(null);
  const [alert, setAlert] = useState(null);
  const [copied, setCopied] = useState(false);
  
  const eventSourceRef = useRef(null);

  // Auto scroll to logs if testing takes time
  const bottomRef = useRef(null);
  useEffect(() => {
    if (loading) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [steps, loading, result, alert]);

  const updateStep = (id, updates) => {
    setSteps(prev => prev.map(s => s.id === id ? { ...s, ...updates } : s));
  };

  const handleVerify = (e) => {
    e.preventDefault();
    if (!name.trim() || !domain.trim()) return;

    // Reset States
    setLoading(true);
    setResult(null);
    setAlert(null);
    setPermutations([]);
    setCopied(false);
    setSteps(INITIAL_STEPS.map(s => ({ ...s, status: 'idle', details: 'Waiting...' })));

    // Clean inputs
    const targetName = name.trim();
    const targetDomain = domain.trim();

    // Initialize Stepper
    updateStep('init', { status: 'active', details: 'Connecting to API server...' });

    // Open EventSource Stream
    const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
    const url = `${API_BASE}/api/stream-verify?name=${encodeURIComponent(targetName)}&domain=${encodeURIComponent(targetDomain)}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        switch (data.event) {
          case 'start':
            updateStep('init', { status: 'success', details: data.message });
            updateStep('perms', { status: 'active', details: 'Generating combination patterns...' });
            break;
            
          case 'cleaned':
            updateStep('init', { status: 'success', details: `Target normalized to domain: ${data.domain}` });
            break;
            
          case 'permutations':
            setPermutations(data.permutations);
            updateStep('perms', { 
              status: 'success', 
              details: `Generated ${data.permutations.length} professional combinations.` 
            });
            updateStep('dns', { status: 'active', details: 'Resolving MX records...' });
            break;
            
          case 'mx_start':
            updateStep('dns', { status: 'active', details: data.message });
            break;
            
          case 'mx_found':
            updateStep('dns', { 
              status: 'success', 
              details: `MX records resolved. Primary mail server: ${data.mx_host}` 
            });
            updateStep('smtp', { status: 'active', details: 'Initiating catch-all checks...' });
            break;
            
          case 'catchall_start':
            updateStep('smtp', { status: 'active', details: data.message });
            break;
            
          case 'port_blocked':
            updateStep('smtp', { 
              status: data.hunter_key_present ? 'warning' : 'error', 
              details: data.hunter_key_present 
                ? 'SMTP connection refused (Port 25 blocked). Falling back to Hunter.io...' 
                : 'SMTP connection refused. Port 25 is blocked by your ISP.' 
            });
            if (!data.hunter_key_present) {
              setAlert({
                type: 'error',
                title: 'Port 25 Blocked',
                desc: 'Your local network blocks SMTP Port 25. To check emails, set a HUNTER_API_KEY in your backend .env file to enable database verifications.'
              });
              es.close();
              setLoading(false);
            }
            break;
            
          case 'catchall_detected':
            updateStep('smtp', { 
              status: data.hunter_key_present ? 'warning' : 'success', 
              details: data.hunter_key_present 
                ? 'Catch-all domain detected. Falling back to Hunter.io database search...' 
                : 'Catch-all domain. Server accepts all mailboxes.' 
            });
            if (!data.hunter_key_present) {
              setAlert({
                type: 'warning',
                title: 'Catch-All Domain',
                desc: `The server for '${targetDomain}' accepts all addresses. We cannot pinpoint the exact mailbox offline. You can manually copy and try the combinations listed below.`
              });
              es.close();
              setLoading(false);
            }
            break;
            
          case 'testing_db':
            updateStep('smtp', { status: 'active', details: `Checking database: ${data.email}...` });
            break;
            
          case 'verify_loop_start':
            updateStep('smtp', { status: 'active', details: data.message });
            break;
            
          case 'testing_email':
            updateStep('smtp', { status: 'active', details: `Testing address: ${data.email}...` });
            break;
            
          case 'success':
            updateStep('smtp', { 
              status: 'success', 
              details: `Email found! Verified via ${data.method.toUpperCase()}.` 
            });
            setResult({ email: data.email, method: data.method });
            es.close();
            setLoading(false);
            break;
            
          case 'fail':
            updateStep('smtp', { status: 'error', details: data.message });
            setAlert({
              type: 'error',
              title: 'No Verified Email',
              desc: 'None of the generated professional permutations are registered. The mail server returned bouncing errors for all configurations.'
            });
            es.close();
            setLoading(false);
            break;
            
          case 'error':
            updateStep('smtp', { status: 'error', details: data.message });
            setAlert({
              type: 'error',
              title: 'Verification Failed',
              desc: data.message
            });
            es.close();
            setLoading(false);
            break;
            
          default:
            break;
        }
      } catch (err) {
        console.error('Error parsing SSE event:', err);
      }
    };

    es.onerror = (err) => {
      console.error('EventSource connection error:', err);
      updateStep('smtp', { status: 'error', details: 'Lost connection to backend server.' });
      setAlert({
        type: 'error',
        title: 'Connection Error',
        desc: 'Could not communicate with the backend FastAPI server. Make sure server.py is running on port 8000.'
      });
      es.close();
      setLoading(false);
    };
  };

  const handleCopy = () => {
    if (!result) return;
    navigator.clipboard.writeText(result.email);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="app-container">
      <h1>Email Finder</h1>
      <p className="subtitle">Verify and pinpoint professional email addresses instantly</p>
      
      <form onSubmit={handleVerify} className="input-form">
        <div className="form-row">
          <label>Full Name</label>
          <input 
            type="text" 
            placeholder="e.g. Rahul Bose" 
            value={name} 
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
            required
          />
        </div>
        <div className="form-row">
          <label>Company Domain / URL</label>
          <input 
            type="text" 
            placeholder="e.g. gmail.com or https://fibr.ai/" 
            value={domain} 
            onChange={(e) => setDomain(e.target.value)}
            disabled={loading}
            required
          />
        </div>
        
        <button type="submit" className="verify-button" disabled={loading}>
          {loading ? (
            <>
              <span className="spinner"></span>
              Verifying...
            </>
          ) : 'Find & Verify Email'}
        </button>
      </form>

      {/* Progress logs & stepper */}
      {(loading || result || alert || permutations.length > 0) && (
        <div className="progress-container">
          <div className="stepper">
            {steps.map((step, idx) => (
              <div key={step.id} className={`step ${step.status}`}>
                <div className="step-icon">
                  {step.status === 'success' ? '✓' : step.status === 'error' ? '✗' : idx + 1}
                </div>
                <div className="step-content">
                  <div className="step-title">{step.title}</div>
                  <div className="step-details">{step.details}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Alert messages (catch-all or port blocked) */}
          {alert && (
            <div className={`alert-card ${alert.type}`}>
              <div className="alert-title">{alert.title}</div>
              <div className="alert-desc">{alert.desc}</div>
            </div>
          )}

          {/* Result Showcase */}
          {result && (
            <div className="result-card">
              <span className="result-badge">Verified Address</span>
              <div className="result-email">{result.email}</div>
              <button 
                onClick={handleCopy} 
                className={`copy-button ${copied ? 'copied' : ''}`}
              >
                {copied ? 'Copied! ✓' : 'Copy Email'}
              </button>
            </div>
          )}

          {/* Manual Combinations List for Catch-All / Bypassed checks */}
          {(alert || (result && result.method === 'hunter')) && permutations.length > 0 && (
            <div style={{ marginTop: '2rem', background: 'rgba(255,255,255,0.02)', padding: '1.25rem', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Generated Permutations
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
                {permutations.map((p, idx) => (
                  <div 
                    key={idx} 
                    style={{ fontSize: '0.9rem', padding: '0.4rem 0.6rem', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-color)', borderRadius: '6px', color: p === result?.email ? 'var(--accent)' : 'var(--text-main)' }}
                  >
                    {p}
                  </div>
                ))}
              </div>
            </div>
          )}
          
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}

export default App;
