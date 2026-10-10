import React, { useState, useEffect, useRef } from 'react';
import './App.css';

// === SVG Icons ===
const TrainIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
    <path d="M4 15.5C4 17.43 5.57 19 7.5 19L6 20.5v.5h12v-.5L16.5 19c1.93 0 3.5-1.57 3.5-3.5V5c0-3.5-3.58-4-8-4s-8 .5-8 4v10.5zm8-12.5c4.78 0 6 1.04 6 2v2H6V5c0-.96 1.22-2 6-2zm-6 6h12v5H6v-5zm2 7a1.5 1.5 0 110-3 1.5 1.5 0 010 3zm8 0a1.5 1.5 0 110-3 1.5 1.5 0 010 3z" />
  </svg>
);

const TargetIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"></circle>
    <circle cx="12" cy="12" r="6"></circle>
    <circle cx="12" cy="12" r="2"></circle>
  </svg>
);

const ChatBubbleIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
  </svg>
);

const SendIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13"></line>
    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
  </svg>
);

const ShieldCheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
    <polyline points="9 12 11 14 15 10"></polyline>
  </svg>
);

const ExternalLinkIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
    <polyline points="15 3 21 3 21 9"></polyline>
    <line x1="10" y1="14" x2="21" y2="3"></line>
  </svg>
);

const ClockIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"></circle>
    <polyline points="12 6 12 12 16 14"></polyline>
  </svg>
);

const MapPinIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
    <circle cx="12" cy="10" r="3"></circle>
  </svg>
);

const CheckCircleIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
    <polyline points="22 4 12 14.01 9 11.01"></polyline>
  </svg>
);

const AlertTriangleIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
    <line x1="12" y1="9" x2="12" y2="13"></line>
    <line x1="12" y1="17" x2="12.01" y2="17"></line>
  </svg>
);

const formatDisplayDate = (isoDateStr) => {
  if (!isoDateStr) return '';
  try {
    const parts = isoDateStr.split('-');
    if (parts.length === 3) {
      const year = parseInt(parts[0], 10);
      const month = parseInt(parts[1], 10) - 1;
      const day = parseInt(parts[2], 10);
      const d = new Date(year, month, day);
      return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    }
  } catch (e) {}
  return isoDateStr;
};

const GOAL_TEMPLATES = [
  {
    title: '🏢 Tidel Park Meeting (Chennai)',
    prompt: "I have a meeting at Tidel Park in Chennai at 10:00 AM on 25 October. I'm travelling from Bengaluru. I want AC 3-tier if possible, prefer a reasonably affordable train, and want to reach the meeting location at least 45 minutes early. Find the best train.",
  },
  {
    title: '🎓 IIT Madras Exam (Chennai)',
    prompt: "Exam at IIT Madras Chennai at 09:00 AM on 25 October 2026. Travelling from Bengaluru. Need at least 1 hour buffer at the venue.",
  },
  {
    title: '💼 BKC Mumbai Business Meet',
    prompt: "I have a business meeting at Bandra Kurla Complex (BKC) Mumbai at 11:00 AM on 2026-10-25 from New Delhi. Prefer Rajdhani Express.",
  },
  {
    title: '💻 HITEC City Interview (Hyderabad)',
    prompt: "Job interview at HITEC City Hyderabad at 09:30 AM on 2026-10-25 from Bengaluru. Need 45 mins buffer.",
  },
];

const TICKETING_TOPICS = [
  {
    icon: '🚆',
    title: 'Class Differences (2A vs 3A)',
    desc: 'Understand berth configurations, bedding, AC & comfort.',
    prompt: 'What is the difference between Second AC (2A) and Third AC (3A) classes?',
  },
  {
    icon: '📋',
    title: 'RAC & Waiting List Rules',
    desc: 'How RAC seating works, chart preparation & GNWL vs RLWL.',
    prompt: 'How does RAC work and can I board the train with an RAC ticket?',
  },
  {
    icon: '⚡',
    title: 'Tatkal Booking Workflows',
    desc: 'Official opening timings (10 AM AC / 11 AM Non-AC) and IRCTC rules.',
    prompt: 'What are the exact booking timings, rules, and procedures for Tatkal tickets?',
  },
  {
    icon: '💸',
    title: 'Cancellation & Refund Policies',
    desc: 'Time-slab deductions (48h, 12h, 4h), clerkage charges & TDR filing.',
    prompt: 'What are the cancellation charges for a confirmed ticket cancelled 24 hours before train departure?',
  },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('planner'); // 'planner' or 'guidance'
  
  // === Goal Planner State ===
  const [plannerPrompt, setPlannerPrompt] = useState(GOAL_TEMPLATES[0].prompt);
  const [showAdvancedForm, setShowAdvancedForm] = useState(false);
  const [origin, setOrigin] = useState('Bengaluru');
  const [venue, setVenue] = useState('Tidel Park');
  const [destCity, setDestCity] = useState('Chennai');
  const [meetingDate, setMeetingDate] = useState('2026-10-25');
  const [meetingTime, setMeetingTime] = useState('10:00');
  const [bufferMinutes, setBufferMinutes] = useState(45);
  const [preferredClass, setPreferredClass] = useState('3A');
  const [preferredTrain, setPreferredTrain] = useState('');
  const [budgetMax, setBudgetMax] = useState('');
  
  const [planningLoading, setPlanningLoading] = useState(false);
  const [journeyPlan, setJourneyPlan] = useState(null);
  const [plannerError, setPlannerError] = useState(null);
  const [traceModalData, setTraceModalData] = useState(null);

  // === Chat Guidance State ===
  const [messages, setMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [systemHealth, setSystemHealth] = useState(null);
  const [sourcesList, setSourcesList] = useState([]);
  const [sourcesModalOpen, setSourcesModalOpen] = useState(false);

  const chatEndRef = useRef(null);

  useEffect(() => {
    fetchHealth();
    fetchSources();
  }, []);

  useEffect(() => {
    if (activeTab === 'guidance') {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, activeTab]);

  const fetchHealth = async () => {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const data = await res.json();
        setSystemHealth(data);
      }
    } catch (e) {
      console.warn('Health check failed:', e);
    }
  };

  const fetchSources = async () => {
    try {
      const res = await fetch('/api/sources');
      if (res.ok) {
        const data = await res.json();
        setSourcesList(data.sources || []);
      }
    } catch (e) {
      console.warn('Failed to load sources:', e);
    }
  };

  // === Journey Planning Actions ===
  const handlePlanJourney = async (e) => {
    if (e) e.preventDefault();
    setPlanningLoading(true);
    setPlannerError(null);

    const payload = showAdvancedForm
      ? {
          origin,
          destination_venue: venue,
          destination_city: destCity,
          meeting_date: meetingDate,
          meeting_time: meetingTime,
          required_arrival_buffer_minutes: Number(bufferMinutes),
          preferred_class: preferredClass || undefined,
          preferred_train_name_or_number: preferredTrain || undefined,
          budget_max: budgetMax ? Number(budgetMax) : undefined,
        }
      : {
          prompt: plannerPrompt,
        };

    try {
      const res = await fetch('/api/journey/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        setPlannerError(data.error || 'Failed to generate journey plan.');
      } else {
        setJourneyPlan(data);
      }
    } catch (err) {
      setPlannerError('Network error connecting to RailSathi planning backend.');
    } finally {
      setPlanningLoading(false);
    }
  };

  const handleRefine = async (refinements) => {
    if (!journeyPlan || planningLoading) return;

    // Guard: Prevent repeatedly triggering identical requests
    const currentReq = journeyPlan.trip_requirements || {};
    let isIdentical = true;
    for (const [key, val] of Object.entries(refinements)) {
      if (currentReq[key] !== val) {
        isIdentical = false;
        break;
      }
    }
    if (isIdentical) {
      return;
    }

    // Explain when a new live request is required but cannot be made due to exhausted quota
    const qInfo = journeyPlan.quota_info;
    if (qInfo?.is_exhausted && !qInfo?.usable_cached_results_exist) {
      setPlannerError(
        `Cannot search new timetable: Upstream RailRadar request budget is exhausted (${qInfo.used_requests}/${qInfo.monthly_limit}). ` +
        `Refinements cannot be queried until quota resets on ${qInfo.reset_date_formatted || qInfo.reset_date}.`
      );
      return;
    }

    setPlanningLoading(true);
    setPlannerError(null);

    const payload = {
      requirements: journeyPlan.trip_requirements,
      ...refinements,
    };

    try {
      const res = await fetch('/api/journey/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok) {
        setJourneyPlan(data);
      } else {
        setPlannerError(data.error || 'Failed to refine plan.');
      }
    } catch (err) {
      setPlannerError('Network error refining journey plan.');
    } finally {
      setPlanningLoading(false);
    }
  };


  // === Chat Guidance Actions ===
  const handleSendChat = async (textToSend) => {
    const query = textToSend || chatInput;
    if (!query.trim() || chatLoading) return;

    const userMsg = { role: 'user', content: query, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
    setMessages((prev) => [...prev, userMsg]);
    setChatInput('');
    setChatLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: query,
          conversation_id: conversationId,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        if (data.conversation_id) setConversationId(data.conversation_id);
        const assistantMsg = {
          role: 'assistant',
          content: data.answer,
          sources: data.sources || [],
          trace: data.trace || [],
          trace_id: data.trace_id,
          status: data.status,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `⚠️ Error: ${data.error || 'Failed to get response'}`,
            status: 'error',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: '⚠️ Network error: Could not reach backend server.',
          status: 'error',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand-wrapper">
          <div className="logo-badge">
            <TrainIcon />
          </div>
          <div className="brand-info">
            <h1>RailSathi AI</h1>
            <span className="tagline">
              <ShieldCheckIcon /> Goal-Based Train Journey Planner & Guidance
            </span>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="nav-tabs">
          <button
            className={`tab-btn ${activeTab === 'planner' ? 'active' : ''}`}
            onClick={() => setActiveTab('planner')}
          >
            <TargetIcon /> <span>Goal Journey Planner</span>
          </button>
          <button
            className={`tab-btn ${activeTab === 'guidance' ? 'active' : ''}`}
            onClick={() => setActiveTab('guidance')}
          >
            <ChatBubbleIcon /> <span>Ticketing Guidance</span>
          </button>
        </div>

        <div className="header-actions">
          <div className="status-chip">
            <span className="status-dot"></span>
            <span>Deterministic Verified Engine</span>
          </div>
          <button className="btn-secondary" onClick={() => setSourcesModalOpen(true)}>
            Sources ({sourcesList.length || 4})
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="main-content">
        {activeTab === 'planner' ? (
          <div className="planner-view">
            {/* Input Hero Section */}
            <div className="planner-hero-card">
              <div className="hero-header">
                <h2>🎯 Plan Your Train Journey by Real-World Goal</h2>
                <p>
                  Tell us where you need to be and when. RailSathi calculates last-mile transit, station deadlines, time buffers, and ranks feasible trains.
                </p>
              </div>

              {/* Goal Template Quick Chips */}
              <div className="template-chips">
                <span className="chip-label">Quick Scenarios:</span>
                {GOAL_TEMPLATES.map((tpl, i) => (
                  <button
                    key={i}
                    className="template-chip"
                    onClick={() => {
                      setPlannerPrompt(tpl.prompt);
                      setShowAdvancedForm(false);
                    }}
                  >
                    {tpl.title}
                  </button>
                ))}
              </div>

              <form onSubmit={handlePlanJourney} className="planner-form">
                {!showAdvancedForm ? (
                  <div className="prompt-input-group">
                    <textarea
                      className="planner-textarea"
                      rows="3"
                      value={plannerPrompt}
                      onChange={(e) => setPlannerPrompt(e.target.value)}
                      placeholder="e.g. I have a meeting at Tidel Park in Chennai at 10:00 AM on 25 October. I'm travelling from Bengaluru. I want AC 3-tier, reach 45 mins early..."
                    />
                    <div className="form-bottom-bar">
                      <button
                        type="button"
                        className="btn-link"
                        onClick={() => setShowAdvancedForm(true)}
                      >
                        ⚙️ Switch to Structured Form
                      </button>
                      <button type="submit" className="btn-primary" disabled={planningLoading}>
                        {planningLoading ? 'Evaluating Feasibility...' : '🚀 Find Best Train'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="structured-form-grid">
                    <div className="form-field">
                      <label>Starting City / Origin</label>
                      <input
                        type="text"
                        value={origin}
                        onChange={(e) => setOrigin(e.target.value)}
                        placeholder="e.g. Bengaluru"
                        required
                      />
                    </div>
                    <div className="form-field">
                      <label>Destination Venue / Landmark</label>
                      <input
                        type="text"
                        value={venue}
                        onChange={(e) => setVenue(e.target.value)}
                        placeholder="e.g. Tidel Park"
                        required
                      />
                    </div>
                    <div className="form-field">
                      <label>Destination City</label>
                      <input
                        type="text"
                        value={destCity}
                        onChange={(e) => setDestCity(e.target.value)}
                        placeholder="e.g. Chennai"
                      />
                    </div>
                    <div className="form-field">
                      <label>Meeting / Event Date</label>
                      <input
                        type="date"
                        value={meetingDate}
                        onChange={(e) => setMeetingDate(e.target.value)}
                        required
                      />
                    </div>
                    <div className="form-field">
                      <label>Meeting Start Time</label>
                      <input
                        type="time"
                        value={meetingTime}
                        onChange={(e) => setMeetingTime(e.target.value)}
                        required
                      />
                    </div>
                    <div className="form-field">
                      <label>Required Buffer at Venue (Minutes)</label>
                      <input
                        type="number"
                        min="0"
                        max="360"
                        value={bufferMinutes}
                        onChange={(e) => setBufferMinutes(e.target.value)}
                        required
                      />
                    </div>
                    <div className="form-field">
                      <label>Preferred Class</label>
                      <select
                        value={preferredClass}
                        onChange={(e) => setPreferredClass(e.target.value)}
                      >
                        <option value="">Any Available Class</option>
                        <option value="3A">AC 3-Tier (3A)</option>
                        <option value="2A">AC 2-Tier (2A)</option>
                        <option value="CC">AC Chair Car (CC)</option>
                        <option value="SL">Sleeper (SL)</option>
                        <option value="3E">AC 3 Economy (3E)</option>
                        <option value="1A">First AC (1A)</option>
                      </select>
                    </div>
                    <div className="form-field">
                      <label>Preferred Train (Optional)</label>
                      <input
                        type="text"
                        value={preferredTrain}
                        onChange={(e) => setPreferredTrain(e.target.value)}
                        placeholder="e.g. Vande Bharat or 20608"
                      />
                    </div>
                    <div className="form-field">
                      <label>Max Budget (₹ INR)</label>
                      <input
                        type="number"
                        value={budgetMax}
                        onChange={(e) => setBudgetMax(e.target.value)}
                        placeholder="e.g. 1500"
                      />
                    </div>

                    <div className="form-actions-full">
                      <button
                        type="button"
                        className="btn-link"
                        onClick={() => setShowAdvancedForm(false)}
                      >
                        💬 Switch to Natural Language
                      </button>
                      <button type="submit" className="btn-primary" disabled={planningLoading}>
                        {planningLoading ? 'Evaluating Feasibility...' : '🚀 Calculate & Rank Trains'}
                      </button>
                    </div>
                  </div>
                )}
              </form>
            </div>

            {/* Planner Error State */}
            {plannerError && (
              <div className="error-banner">
                <AlertTriangleIcon />
                <span>{plannerError}</span>
              </div>
            )}

            {/* Planner Results Section */}
            {journeyPlan && (
              <div className="plan-results-container">
                {/* Goal Summary Ribbon */}
                <div className="goal-summary-ribbon">
                  <div className="ribbon-target">
                    <span className="ribbon-badge">GOAL</span>
                    <h3>
                      Reach <strong>{journeyPlan.trip_requirements.destination_venue}</strong> by{' '}
                      <span className="highlight-time">{journeyPlan.trip_requirements.meeting_time}</span> on{' '}
                      <span>{formatDisplayDate(journeyPlan.trip_requirements.meeting_date)}</span>
                    </h3>
                  </div>
                  <div className="ribbon-details">
                    <span>Origin: <strong>{journeyPlan.trip_requirements.origin}</strong></span>
                    <span>Required Buffer: <strong>{journeyPlan.trip_requirements.required_arrival_buffer_minutes}m</strong></span>
                    {journeyPlan.trip_requirements.preferred_class && (
                      <span>Class: <strong>{journeyPlan.trip_requirements.preferred_class}</strong></span>
                    )}
                  </div>
                </div>

                {/* Candidate Stations Resolution */}
                <div className="resolved-stations-bar">
                  <div className="station-group">
                    <span className="station-group-title">🚉 Departure Hubs:</span>
                    {journeyPlan.candidate_origin_stations?.slice(0, 3).map((st) => (
                      <span key={st.station_code} className="station-tag">
                        {st.station_code} ({st.station_name})
                      </span>
                    ))}
                  </div>
                  <div className="station-group">
                    <span className="station-group-title">🎯 Arrival Stations near Venue:</span>
                    {journeyPlan.candidate_destination_stations?.slice(0, 3).map((st) => (
                      <span key={st.station_code} className="station-tag">
                        {st.station_code} ({st.station_name}) — ~{st.distance_to_venue_km}km
                      </span>
                    ))}
                  </div>
                </div>

                {/* CLARIFICATION REQUIRED OR BEST MATCH OR NO FEASIBLE HERO CARD */}
                {journeyPlan.status === 'clarification_required' ? (
                  <div className="no-feasible-card" style={{ borderColor: '#f59e0b', background: 'rgba(245, 158, 11, 0.08)' }}>
                    <AlertTriangleIcon />
                    <div style={{ width: '100%' }}>
                      <h3 style={{ color: '#d97706' }}>⚠️ Location Clarification Required</h3>
                      <p>{journeyPlan.clarification_question || journeyPlan.summary}</p>
                      {journeyPlan.resolved_destination?.clarification_options?.length > 0 && (
                        <div className="template-chips" style={{ marginTop: '0.75rem' }}>
                          <span className="chip-label" style={{ fontWeight: 600 }}>Suggested Locations:</span>
                          {journeyPlan.resolved_destination.clarification_options.map((opt, i) => (
                            <button
                              key={i}
                              type="button"
                              className="template-chip"
                              style={{ borderColor: '#f59e0b', color: '#b45309', background: '#fffbeb' }}
                              onClick={() => {
                                setVenue(opt);
                                setPlannerPrompt(`I have a meeting at ${opt} at ${meetingTime} on ${meetingDate}. Travel from ${origin || 'Bengaluru'}.`);
                              }}
                            >
                              📍 {opt}
                            </button>
                          ))}
                        </div>
                      )}
                      <p style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: '#64748b' }}>
                        {journeyPlan.tradeoff_explanation}
                      </p>
                    </div>
                  </div>
                ) : (journeyPlan.search_outcome === 'quota_exhausted' || (journeyPlan.status === 'monthly_quota_exhausted' && !journeyPlan.best_match)) ? (
                  <div className="quota-exhausted-card">
                    <div className="quota-card-header">
                      <AlertTriangleIcon />
                      <h3>Train Data Request Budget Exhausted</h3>
                      <span className="unverified-pill">⚠️ Feasibility Unverified</span>
                    </div>
                    <p className="quota-main-msg">
                      Train data request budget exhausted. We could not verify whether a train meets your deadline. Cached results, if available, are shown separately.
                    </p>
                    <div className="quota-metrics-grid">
                      <div className="quota-metric-item">
                        <span className="quota-metric-lbl">Requests Used</span>
                        <span className="quota-metric-val">
                          {journeyPlan.quota_info ? `${journeyPlan.quota_info.used_requests} / ${journeyPlan.quota_info.monthly_limit}` : 'Exhausted'}
                        </span>
                      </div>
                      <div className="quota-metric-item">
                        <span className="quota-metric-lbl">Remaining Requests</span>
                        <span className="quota-metric-val">
                          {journeyPlan.quota_info ? journeyPlan.quota_info.remaining_requests : 0} ({journeyPlan.quota_info?.reserve_held || 0} reserve held)
                        </span>
                      </div>
                      <div className="quota-metric-item">
                        <span className="quota-metric-lbl">Verified Reset Time</span>
                        <span className="quota-metric-val">
                          {journeyPlan.quota_info?.reset_date_formatted || journeyPlan.quota_info?.reset_date || 'Next billing cycle'}
                        </span>
                      </div>
                      <div className="quota-metric-item">
                        <span className="quota-metric-lbl">Cached Results Available</span>
                        <span className="quota-metric-val">
                          {journeyPlan.quota_info?.usable_cached_results_exist ? 'Yes (Shown below)' : 'None found for this corridor'}
                        </span>
                      </div>
                      {journeyPlan.quota_info?.last_successful_retrieval_at && (
                        <div className="quota-metric-item">
                          <span className="quota-metric-lbl">Last Successful Schedule Retrieval</span>
                          <span className="quota-metric-val">
                            {journeyPlan.quota_info.last_successful_retrieval_at}
                          </span>
                        </div>
                      )}
                    </div>
                    <p className="quota-disclaimer">
                      ℹ️ Note: We do not label this journey impossible because train schedules could not be verified due to provider request limits.
                    </p>
                  </div>
                ) : (journeyPlan.search_outcome === 'search_data_unavailable' || journeyPlan.status === 'provider_unavailable' || (journeyPlan.status === 'insufficient_data' && !journeyPlan.best_match && !journeyPlan.infeasible_options?.length)) ? (
                  <div className="data-unavailable-card">
                    <div className="quota-card-header">
                      <AlertTriangleIcon />
                      <h3>Train Schedule Data Unavailable</h3>
                      <span className="unverified-pill">⚠️ Feasibility Unverified</span>
                    </div>
                    <p>{journeyPlan.summary}</p>
                    <p className="quota-disclaimer">{journeyPlan.tradeoff_explanation}</p>
                  </div>
                ) : journeyPlan.best_match ? (
                  <div className="hero-recommendation-card">
                    <div className="rec-header">
                      <div className="rec-badge-row">
                        <span className="badge-best-match">🏆 TOP FEASIBLE RECOMMENDATION</span>
                        {journeyPlan.quota_info?.is_exhausted && (
                          <span className="cached-eval-badge">📦 Evaluated from Cached Timetable</span>
                        )}
                        <span className="badge-buffer-success">
                          ✅ Reaches Venue {journeyPlan.best_match.actual_arrival_buffer_minutes}m Before Meeting
                        </span>
                      </div>
                      <h2 className="train-title">
                        {journeyPlan.best_match.train_service.train_name}{' '}
                        <span className="train-num">#{journeyPlan.best_match.train_service.train_number}</span>
                      </h2>
                    </div>

                    {/* Timeline Journey Visualizer */}
                    <div className="journey-timeline">
                      <div className="timeline-node">
                        <span className="node-time">{journeyPlan.best_match.train_service.departure_time}</span>
                        <span className="node-station">{journeyPlan.best_match.train_service.origin_station_name}</span>
                        <span className="node-sub">({journeyPlan.best_match.train_service.origin_station_code})</span>
                      </div>

                      <div className="timeline-segment">
                        <span className="segment-duration">
                          {Math.floor(journeyPlan.best_match.train_service.duration_minutes / 60)}h{' '}
                          {journeyPlan.best_match.train_service.duration_minutes % 60}m train ride
                        </span>
                        <div className="segment-line"></div>
                      </div>

                      <div className="timeline-node">
                        <span className="node-time">
                          {journeyPlan.best_match.train_service.arrival_time}
                          {journeyPlan.best_match.train_service.day_offset > 0 && (
                            <span className="day-offset-pill">+{journeyPlan.best_match.train_service.day_offset}d</span>
                          )}
                        </span>
                        <span className="node-station">{journeyPlan.best_match.train_service.destination_station_name}</span>
                        <span className="node-sub">({journeyPlan.best_match.train_service.destination_station_code})</span>
                      </div>

                      <div className="timeline-segment transfer">
                        <span className="segment-duration">
                          ~{journeyPlan.best_match.last_mile_duration_minutes}m cab ({journeyPlan.best_match.last_mile_distance_km}km)
                        </span>
                        <div className="segment-line transfer-line"></div>
                      </div>

                      <div className="timeline-node destination">
                        <span className="node-time venue-time">
                          ⏰ {journeyPlan.best_match.actual_arrival_buffer_minutes}m Buffer
                        </span>
                        <span className="node-station">{journeyPlan.best_match.last_mile_destination_venue}</span>
                        <span className="node-sub highlight-meet">Meeting: {journeyPlan.trip_requirements.meeting_time}</span>
                      </div>
                    </div>

                    {/* Features & Breakdown */}
                    <div className="rec-details-grid">
                      <div className="rec-detail-item">
                        <span className="detail-lbl">Recommended Class & Fare</span>
                        <span className="detail-val">
                          {journeyPlan.best_match.recommended_fare
                            ? `${journeyPlan.best_match.recommended_class || '3A'} — ₹${journeyPlan.best_match.recommended_fare} (${journeyPlan.best_match.fare_quote?.quota_code || 'GN'} Quota)`
                            : `${journeyPlan.best_match.recommended_class || '3A'} — Fare on IRCTC Handoff`}
                        </span>
                      </div>
                      <div className="rec-detail-item">
                        <span className="detail-lbl">Data Source & Provider</span>
                        <span className="detail-val">
                          {journeyPlan.best_match.train_service.data_source}
                          {journeyPlan.best_match.train_service.verified_at && (
                            <span className="verified-time"> ({journeyPlan.best_match.train_service.verified_at.substring(0, 10)})</span>
                          )}
                        </span>
                      </div>
                      <div className="rec-detail-item">
                        <span className="detail-lbl">Deadline Compliance</span>
                        <span className="detail-val text-success">
                          Latest acceptable station arrival was {new Date(journeyPlan.best_match.latest_acceptable_station_arrival_iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} (Arrives {journeyPlan.best_match.train_service.arrival_time})
                        </span>
                      </div>
                    </div>

                    {/* Official IRCTC Booking Action */}
                    {journeyPlan.best_match.booking_handoff && (
                      <div className="booking-handoff-banner">
                        <div className="handoff-info">
                          <h4>Official IRCTC Booking Handoff</h4>
                          <p>{journeyPlan.best_match.booking_handoff.disclaimer}</p>
                        </div>
                        <a
                          href={journeyPlan.best_match.booking_handoff.booking_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn-book-irctc"
                        >
                          Book on IRCTC <ExternalLinkIcon />
                        </a>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="no-feasible-card">
                    <AlertTriangleIcon />
                    <div>
                      <h3>No Feasible Direct Trains Found for Exact Deadline</h3>
                      <p>{journeyPlan.tradeoff_explanation || journeyPlan.summary}</p>
                    </div>
                  </div>
                )}

                {/* FEASIBLE ALTERNATIVES LIST */}
                {journeyPlan.feasible_alternatives?.length > 0 && (
                  <div className="alternatives-section">
                    <h3>🚆 Feasible Alternative Direct Trains</h3>
                    <div className="alternatives-grid">
                      {journeyPlan.feasible_alternatives.map((alt) => (
                        <div key={alt.candidate_id} className="alt-card">
                          <div className="alt-card-header">
                            <h4>
                              {alt.train_service.train_name}{' '}
                              <span className="alt-num">#{alt.train_service.train_number}</span>
                            </h4>
                            <span className="badge-buffer">
                              +{alt.actual_arrival_buffer_minutes}m buffer
                            </span>
                          </div>
                          <p className="alt-timing">
                            Departs {alt.train_service.departure_time} ({alt.train_service.origin_station_code}) → Arrives {alt.train_service.arrival_time} {alt.train_service.day_offset > 0 ? `(+${alt.train_service.day_offset}d)` : ''} ({alt.train_service.destination_station_code})
                          </p>
                          <div className="alt-footer">
                            <span className="alt-fare">
                              {alt.recommended_fare
                                ? `${alt.recommended_class || '3A'} (₹${alt.recommended_fare})`
                                : `${alt.recommended_class || '3A'} (Fare at IRCTC)`}
                            </span>
                            {alt.booking_handoff && (
                              <a
                                href={alt.booking_handoff.booking_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn-link-small"
                              >
                                IRCTC Search <ExternalLinkIcon />
                              </a>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* CONNECTING TRAINS & MULTI-LEG ROUTES SECTION */}
                {journeyPlan.connecting_options?.length > 0 && (
                  <div className="alternatives-section" style={{ marginTop: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                      <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        🔁 Connecting Train Options (1 Interchange)
                      </h3>
                      <span className="badge-buffer-success" style={{ fontSize: '0.75rem' }}>
                        {journeyPlan.connecting_options.filter(c => c.is_feasible).length} Feasible Routes
                      </span>
                    </div>
                    <div className="alternatives-grid">
                      {journeyPlan.connecting_options.map((conn) => (
                        <div key={conn.candidate_id} className="alt-card" style={{ borderLeft: conn.is_feasible ? '4px solid #10b981' : '4px solid #ef4444' }}>
                          <div className="alt-card-header">
                            <div>
                              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6366f1', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                Via {conn.interchange_station_name} ({conn.interchange_station_code})
                              </span>
                              <h4 style={{ marginTop: '0.25rem' }}>
                                {conn.leg_1.train_service.train_name} ➔ {conn.leg_2.train_service.train_name}
                              </h4>
                            </div>
                            <span className={conn.is_feasible ? "badge-buffer" : "badge-late"}>
                              {conn.is_feasible ? `+${conn.actual_arrival_buffer_minutes}m buffer` : 'Misses Deadline'}
                            </span>
                          </div>

                          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '0.75rem', borderRadius: '6px', margin: '0.5rem 0', fontSize: '0.85rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                              <span><strong>Leg 1:</strong> #{conn.leg_1.train_service.train_number} ({conn.leg_1.from_station_code} {conn.leg_1.train_service.departure_time} ➔ {conn.leg_1.to_station_code} {conn.leg_1.train_service.arrival_time})</span>
                              {conn.leg_1.booking_handoff && (
                                <a href={conn.leg_1.booking_handoff.booking_url} target="_blank" rel="noopener noreferrer" style={{ color: '#6366f1', textDecoration: 'underline' }}>Book Leg 1</a>
                              )}
                            </div>
                            <div style={{ color: '#f59e0b', fontSize: '0.8rem', paddingLeft: '0.5rem', borderLeft: '2px solid #f59e0b', margin: '0.25rem 0' }}>
                              ⏳ {conn.layover_minutes}m layover at {conn.interchange_station_name}
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.35rem' }}>
                              <span><strong>Leg 2:</strong> #{conn.leg_2.train_service.train_number} ({conn.leg_2.from_station_code} {conn.leg_2.train_service.departure_time} ➔ {conn.leg_2.to_station_code} {conn.leg_2.train_service.arrival_time})</span>
                              {conn.leg_2.booking_handoff && (
                                <a href={conn.leg_2.booking_handoff.booking_url} target="_blank" rel="noopener noreferrer" style={{ color: '#6366f1', textDecoration: 'underline' }}>Book Leg 2</a>
                              )}
                            </div>
                          </div>

                          <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: '0.25rem 0' }}>
                            {conn.explanation}
                          </p>

                          <div className="alt-footer">
                            <span className="alt-fare">
                              Total Time: {Math.floor(conn.total_journey_duration_minutes / 60)}h {conn.total_journey_duration_minutes % 60}m
                              {conn.total_estimated_fare ? ` • Est. Fare ₹${conn.total_estimated_fare}` : ''}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}



                {/* INFEASIBLE / DOES NOT MEET REQUIREMENTS SECTION */}
                {journeyPlan.infeasible_options?.length > 0 && (
                  <div className="infeasible-section">
                    <h3 className="infeasible-title">❌ Evaluated Trains That Do NOT Meet Your Requirements</h3>
                    <div className="infeasible-list">
                      {journeyPlan.infeasible_options.map((inf) => (
                        <div key={inf.candidate_id} className="infeasible-card">
                          <div className="inf-header">
                            <span className="inf-train">
                              {inf.train_service.train_name} (#{inf.train_service.train_number})
                            </span>
                            <span className="badge-late">Misses Deadline</span>
                          </div>
                          <p className="inf-schedule">
                            Departs {inf.train_service.departure_time} → Arrives {inf.train_service.arrival_time} at {inf.train_service.destination_station_name}
                          </p>
                          <div className="inf-reasons">
                            {inf.hard_constraint_violations.map((v, vi) => (
                              <span key={vi} className="violation-tag">
                                ⚠️ {v}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Quick Refinement Action Toolbar */}
                <div className="refine-toolbar">
                  <span className="refine-lbl">⚡ Quick Refine:</span>
                  <button
                    className="btn-refine"
                    disabled={planningLoading || journeyPlan.trip_requirements?.required_arrival_buffer_minutes === 30}
                    onClick={() => handleRefine({ required_arrival_buffer_minutes: 30 })}
                  >
                    Set 30m Buffer
                  </button>
                  <button
                    className="btn-refine"
                    disabled={planningLoading || journeyPlan.trip_requirements?.preferred_class === 'CC'}
                    onClick={() => handleRefine({ preferred_class: 'CC' })}
                  >
                    Filter AC Chair Car (CC)
                  </button>
                  <button
                    className="btn-refine"
                    disabled={planningLoading || journeyPlan.trip_requirements?.meeting_time === '11:00'}
                    onClick={() => handleRefine({ meeting_time: '11:00' })}
                  >
                    Postpone Meeting to 11:00 AM
                  </button>
                  <button
                    className="btn-refine"
                    disabled={planningLoading || journeyPlan.trip_requirements?.meeting_time === '14:00'}
                    onClick={() => handleRefine({ meeting_time: '14:00' })}
                  >
                    Afternoon (02:00 PM)
                  </button>
                  {journeyPlan.quota_info?.is_exhausted && (
                    <span className="quota-refine-hint">
                      ℹ️ Re-evaluates from cached schedules. Quick refine does not restore upstream RailRadar quota.
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Ticketing Guidance Chat View */
          <div className="chat-view">
            {messages.length === 0 ? (
              <div className="chat-welcome-container">
                <div className="welcome-hero">
                  <h2>💬 Indian Railways Ticketing Guidance</h2>
                  <p>
                    Ask any question about IRCTC booking rules, RAC/WL status, ticket classes, or cancellation refund policies.
                  </p>
                </div>

                <div className="quick-topics-grid">
                  {TICKETING_TOPICS.map((topic, i) => (
                    <div
                      key={i}
                      className="topic-card"
                      onClick={() => handleSendChat(topic.prompt)}
                    >
                      <div className="topic-icon">{topic.icon}</div>
                      <h3>{topic.title}</h3>
                      <p>{topic.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="chat-messages-container">
                {messages.map((m, idx) => (
                  <div key={idx} className={`message-bubble ${m.role}`}>
                    <div className="message-header">
                      <span className="message-sender">
                        {m.role === 'user' ? '👤 Passenger' : '🚆 RailSathi AI'}
                      </span>
                      <span className="message-time">{m.timestamp}</span>
                    </div>

                    <div className="message-text">
                      {m.content.split('\n').map((line, li) => (
                        <p key={li}>{line}</p>
                      ))}
                    </div>

                    {m.sources?.length > 0 && (
                      <div className="message-sources">
                        <span className="sources-label">Sources:</span>
                        {m.sources.map((s, si) => (
                          <a
                            key={si}
                            href={s.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="source-chip"
                          >
                            {s.title} ({s.last_verified_at}) <ExternalLinkIcon />
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {chatLoading && (
                  <div className="message-bubble assistant loading">
                    <div className="typing-dots">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                    <span>Consulting verified railway sources...</span>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}

            {/* Chat Input Bar */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendChat();
              }}
              className="chat-input-form"
            >
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask about train ticket classes, RAC/WL status, Tatkal, or refund rules..."
                className="chat-input"
              />
              <button type="submit" className="btn-send" disabled={chatLoading}>
                <SendIcon />
              </button>
            </form>
          </div>
        )}
      </main>

      {/* Verified Sources Modal */}
      {sourcesModalOpen && (
        <div className="modal-backdrop" onClick={() => setSourcesModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>📚 Verified Indian Railways Knowledge Sources</h3>
              <button className="btn-close" onClick={() => setSourcesModalOpen(false)}>
                ✕
              </button>
            </div>
            <div className="modal-body">
              <p className="modal-desc">
                RailSathi AI only utilizes authoritative, verified data sources. Static timetables establish scheduled services without fabricating live inventory.
              </p>
              <div className="sources-table">
                {sourcesList.map((s) => (
                  <div key={s.source_id} className="source-item">
                    <div className="source-item-header">
                      <strong>{s.title}</strong>
                      <span className="badge-verified">Verified: {s.last_verified_at}</span>
                    </div>
                    <span className="source-publisher">{s.publisher}</span>
                    <a
                      href={s.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="source-link"
                    >
                      {s.source_url} <ExternalLinkIcon />
                    </a>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
