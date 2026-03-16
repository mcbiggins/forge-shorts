/**
 * Forge Shorts — React Page Component
 * Drop into your existing Forge frontend as a new route/section.
 *
 * Add to your sidebar nav:
 *   { id: 'shorts', label: 'Forge Shorts', icon: <ScissorsIcon />, badge: 'AI' }
 *
 * Add to your router:
 *   <Route path="/shorts" element={<ForgeShorts />} />
 *
 * Expects a backend API at /api/shorts/* — see API_BASE below.
 * Replace with your actual base URL / axios instance as needed.
 */

import { useState, useEffect, useCallback } from 'react';

const API_BASE = '/api/shorts';

// ── Design tokens — matches Forge dark theme exactly ──────────────────────────
const C = {
  bg:    '#0e0f10',
  side:  '#131517',
  panel: '#191b1e',
  card:  '#1e2124',
  line:  'rgba(255,255,255,0.07)',
  t1:    '#e1e3e5',   // primary text
  t2:    '#7d8186',   // secondary text
  t3:    '#4a4d52',   // muted text
  teal:  '#0ec8e8',
  tealB: 'rgba(14,200,232,0.12)',
  tealR: 'rgba(14,200,232,0.26)',
  grn:   '#22c55e',   grnB: 'rgba(34,197,94,0.13)',
  prp:   '#8b5cf6',   prpB: 'rgba(139,92,246,0.13)',
  red:   '#ef4444',   redB: 'rgba(239,68,68,0.13)',
  yel:   '#f59e0b',   yelB: 'rgba(245,158,11,0.13)',
};

const SEG_COLORS = [C.teal, '#a78bfa', '#34d399', '#fb923c'];

// ── Utilities ─────────────────────────────────────────────────────────────────

function fmtSec(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function StatusPill({ status }) {
  const cfg = {
    complete:     { label: 'Complete',     color: C.grn, bg: C.grnB },
    rendering:    { label: 'Rendering',    color: C.prp, bg: C.prpB },
    exporting:    { label: 'Exporting',    color: C.prp, bg: C.prpB },
    transcribing: { label: 'Transcribing', color: C.yel, bg: C.yelB },
    selecting:    { label: 'Selecting',    color: C.teal, bg: C.tealB },
    building:     { label: 'Building',     color: C.teal, bg: C.tealB },
    discovering:  { label: 'Discovering',  color: C.yel, bg: C.yelB },
    queued:       { label: 'Queued',       color: C.t2,  bg: 'rgba(125,129,134,0.12)' },
    failed:       { label: 'Failed',       color: C.red, bg: C.redB },
  }[status] || { label: status, color: C.t2, bg: 'rgba(125,129,134,0.12)' };

  return (
    <span style={{
      fontSize: 11, fontWeight: 500, padding: '3px 10px', borderRadius: 20,
      color: cfg.color, background: cfg.bg, letterSpacing: '0.02em', whiteSpace: 'nowrap',
    }}>
      {cfg.label}
    </span>
  );
}

function Dot({ color = C.grn }) {
  return (
    <span style={{
      width: 7, height: 7, borderRadius: '50%', background: color,
      display: 'inline-block', flexShrink: 0,
    }} />
  );
}

function Toggle({ on, onChange }) {
  return (
    <div
      onClick={() => onChange(!on)}
      style={{
        width: 40, height: 22, borderRadius: 11, cursor: 'pointer',
        background: on ? C.teal : 'rgba(255,255,255,0.1)',
        position: 'relative', transition: 'background 0.2s', flexShrink: 0,
      }}
    >
      <div style={{
        position: 'absolute', top: 3, left: on ? 21 : 3,
        width: 16, height: 16, borderRadius: '50%', background: '#fff',
        transition: 'left 0.18s',
      }} />
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 600, letterSpacing: '0.09em', color: C.t3,
      textTransform: 'uppercase', marginBottom: 14,
    }}>
      {children}
    </div>
  );
}

function EmptyState({ message }) {
  return (
    <div style={{ padding: '40px 20px', textAlign: 'center', color: C.t3, fontSize: 13 }}>
      {message}
    </div>
  );
}

// ── Queue Panel ───────────────────────────────────────────────────────────────

function QueuePanel({ jobs, selectedId, onSelectJob, loading }) {
  if (loading) return <EmptyState message="Loading jobs..." />;
  if (!jobs.length) return <EmptyState message="No jobs yet. Drop a video into clippy/shorts/ to get started." />;

  return (
    <div>
      {jobs.map(job => (
        <div
          key={job.id}
          onClick={() => onSelectJob(job.id, job.status)}
          style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
            borderBottom: `1px solid ${C.line}`, cursor: 'pointer',
            background: job.id === selectedId ? C.tealB : 'transparent',
            transition: 'background 0.15s',
          }}
        >
          <div style={{
            width: 32, height: 32, borderRadius: 6, background: C.card,
            border: `1px solid ${C.line}`, display: 'flex', alignItems: 'center',
            justifyContent: 'center', fontSize: 12, color: C.t2, flexShrink: 0,
          }}>
            ▶
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 13, fontWeight: 500, color: C.t1, marginBottom: 2,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {job.source_file?.split('/').pop() ?? job.id}
            </div>
            <div style={{ fontSize: 11, color: C.t2, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {job.metadata?.duration_sec && (
                <span>{fmtSec(job.metadata.duration_sec)}</span>
              )}
              {job.metadata?.word_count && (
                <><span style={{ color: C.t3 }}>·</span><span>{job.metadata.word_count.toLocaleString()} words</span></>
              )}
            </div>
            {job.error && (
              <div style={{ fontSize: 10, color: C.red, marginTop: 3 }}>{job.error}</div>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            {job.status === 'complete' && job.metadata?.segment_count != null && (
              <span style={{ fontSize: 11, color: C.t2, whiteSpace: 'nowrap' }}>
                {job.metadata.segment_count} shorts
              </span>
            )}
            <StatusPill status={job.status} />
            <span style={{ fontSize: 10, color: C.t3, whiteSpace: 'nowrap' }}>
              {new Date(job.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Segments Panel ────────────────────────────────────────────────────────────

function SegmentsPanel({ job, segments, loading }) {
  if (loading) return <EmptyState message="Loading segments..." />;

  if (!job) return <EmptyState message="Select a job from the Queue tab to view its segments." />;
  if (job.status !== 'complete') {
    return <EmptyState message={`Job is ${job.status} — segments will appear here when processing is complete.`} />;
  }
  if (!segments?.length) return <EmptyState message="No segments found for this job." />;

  const fileName = job.source_file?.split('/').pop() ?? '';

  // Estimate video duration from last segment end time if not in metadata
  const videoDur = job.metadata?.duration_sec
    || Math.max(...segments.map(s => s.end_sec)) + 10;

  return (
    <div>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
        borderBottom: `1px solid ${C.line}`,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, color: C.t2, marginBottom: 1 }}>Source: {fileName}</div>
          <div style={{ fontSize: 11, color: C.t3 }}>
            {fmtSec(videoDur)} · {segments.length} segments selected by Claude
          </div>
        </div>
        <StatusPill status="complete" />
      </div>

      {/* Timeline map */}
      <div style={{ padding: '14px 16px 12px' }}>
        <div style={{
          fontSize: 10, color: C.t3, letterSpacing: '0.07em',
          textTransform: 'uppercase', marginBottom: 7,
        }}>
          Segment Map — Full Video
        </div>
        <div style={{
          position: 'relative', height: 26, background: C.card,
          borderRadius: 6, overflow: 'hidden', border: `1px solid ${C.line}`,
        }}>
          {segments.map((seg, i) => {
            const left = (seg.start_sec / videoDur) * 100;
            const width = Math.max(((seg.end_sec - seg.start_sec) / videoDur) * 100, 0.5);
            return (
              <div
                key={seg.id}
                title={seg.title}
                style={{
                  position: 'absolute', top: 0, bottom: 0,
                  left: `${left}%`, width: `${width}%`,
                  background: SEG_COLORS[i % SEG_COLORS.length], opacity: 0.85,
                }}
              />
            );
          })}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
          <span style={{ fontSize: 10, color: C.t3 }}>0:00</span>
          <span style={{ fontSize: 10, color: C.t3 }}>{fmtSec(videoDur)}</span>
        </div>
      </div>

      {/* Segment cards */}
      <div style={{ padding: '0 12px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {segments.map((seg, i) => {
          const color = SEG_COLORS[i % SEG_COLORS.length];
          const dur = seg.end_sec - seg.start_sec;
          return (
            <div
              key={seg.id}
              style={{
                background: C.card, border: `1px solid ${C.line}`,
                borderLeft: `3px solid ${color}`, borderRadius: '0 8px 8px 0',
                padding: '11px 14px',
              }}
            >
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginBottom: 7, flexWrap: 'wrap', gap: 6,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color, fontFamily: 'monospace' }}>
                    {i.toString().padStart(2, '0')}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 500, color: C.t1 }}>{seg.title}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 11, color: C.t2, fontFamily: 'monospace' }}>
                    {fmtSec(seg.start_sec)} → {fmtSec(seg.end_sec)}
                  </span>
                  <span style={{
                    fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 4,
                    background: `${color}20`, color,
                  }}>
                    {Math.round(dur)}s
                  </span>
                  {seg.output_file && (
                    <span style={{
                      fontSize: 10, padding: '2px 7px', borderRadius: 4,
                      background: C.grnB, color: C.grn,
                    }}>
                      done
                    </span>
                  )}
                </div>
              </div>
              {seg.hook && (
                <div style={{
                  fontSize: 12, color: C.t1, marginBottom: 5, fontStyle: 'italic', lineHeight: 1.5, opacity: 0.9,
                }}>
                  "{seg.hook}"
                </div>
              )}
              {seg.rationale && (
                <div style={{ fontSize: 11, color: C.t2, lineHeight: 1.4 }}>{seg.rationale}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Outputs Panel ─────────────────────────────────────────────────────────────

function OutputsPanel({ outputs, loading }) {
  if (loading) return <EmptyState message="Loading outputs..." />;
  if (!outputs.length) return <EmptyState message="No outputs yet. Complete a job to see finished shorts here." />;

  return (
    <div style={{ padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 7 }}>
      {outputs.map(seg => {
        const fileName = seg.output_file?.split('/').pop() ?? 'unknown.mp4';
        return (
          <div
            key={seg.id}
            style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px',
              background: C.card, border: `1px solid ${C.line}`, borderRadius: 8,
            }}
          >
            <div style={{
              width: 32, height: 32, borderRadius: 6, background: C.tealB,
              border: `1px solid ${C.tealR}`, display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontSize: 12, color: C.teal, flexShrink: 0,
            }}>
              ▶
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 12, fontWeight: 500, color: C.t1, overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 2,
              }}>
                {fileName}
              </div>
              <div style={{ fontSize: 11, color: C.t2 }}>
                {fmtSec(seg.end_sec - seg.start_sec)} · {seg.title}
              </div>
            </div>
            <a
              href={`${API_BASE}/download/${seg.id}`}
              download={fileName}
              style={{
                fontSize: 11, fontWeight: 500, padding: '5px 12px',
                background: C.tealB, border: `1px solid ${C.tealR}`,
                borderRadius: 6, color: C.teal, textDecoration: 'none',
                whiteSpace: 'nowrap',
              }}
            >
              ↓ Download
            </a>
          </div>
        );
      })}
    </div>
  );
}

// ── Settings Panel ────────────────────────────────────────────────────────────

function SettingsPanel({
  watcherActive, setWatcherActive,
  settings, onSettingChange,
  onProcessFile,
}) {
  const { minDur, targetDur, maxDur, segCount, wordsPerGroup } = settings;

  return (
    <div style={{
      width: 290, flexShrink: 0, background: C.panel, borderLeft: `1px solid ${C.line}`,
      display: 'flex', flexDirection: 'column', overflowY: 'auto',
    }}>
      <div style={{ padding: '16px 18px', flex: 1, display: 'flex', flexDirection: 'column', gap: 22 }}>

        {/* Watcher */}
        <div>
          <SectionLabel>Watcher Status</SectionLabel>
          <div style={{
            background: C.card, border: `1px solid ${watcherActive ? C.tealR : C.line}`,
            borderRadius: 8, padding: '12px 14px', display: 'flex',
            alignItems: 'center', justifyContent: 'space-between', transition: 'border-color 0.2s',
          }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 3 }}>
                <Dot color={watcherActive ? C.teal : 'rgba(255,255,255,0.15)'} />
                <span style={{ fontSize: 13, fontWeight: 500, color: watcherActive ? C.teal : C.t2 }}>
                  {watcherActive ? 'Active' : 'Stopped'}
                </span>
              </div>
              <div style={{ fontSize: 11, color: C.t3 }}>Watching clippy/shorts/</div>
            </div>
            <Toggle on={watcherActive} onChange={setWatcherActive} />
          </div>
        </div>

        {/* Duration */}
        <div>
          <SectionLabel>Segment Duration</SectionLabel>
          <div style={{
            background: C.card, border: `1px solid ${C.line}`, borderRadius: 8,
            padding: '14px', display: 'flex', flexDirection: 'column', gap: 14,
          }}>
            {[
              { label: 'Min', key: 'minDur', val: minDur, min: 10, max: targetDur, color: C.grn },
              { label: 'Target', key: 'targetDur', val: targetDur, min: minDur, max: maxDur, color: C.teal },
              { label: 'Max', key: 'maxDur', val: maxDur, min: targetDur, max: 120, color: C.yel },
            ].map(({ label, key, val, min, max, color }) => (
              <div key={key}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: C.t2 }}>{label}</span>
                  <span style={{ fontSize: 13, fontWeight: 500, color, fontFamily: 'monospace' }}>{val}s</span>
                </div>
                <input
                  type="range"
                  min={min} max={max} step={5} value={val}
                  onChange={e => onSettingChange(key, Number(e.target.value))}
                  style={{ width: '100%', accentColor: color }}
                />
              </div>
            ))}
            <div style={{
              padding: '7px 10px', background: C.panel, borderRadius: 6,
              fontSize: 11, color: C.t3, lineHeight: 1.5,
            }}>
              Claude targets {targetDur}s, rejects anything outside {minDur}–{maxDur}s
            </div>
          </div>
        </div>

        {/* Processing */}
        <div>
          <SectionLabel>Processing Settings</SectionLabel>
          <div style={{
            background: C.card, border: `1px solid ${C.line}`, borderRadius: 8,
            padding: '14px', display: 'flex', flexDirection: 'column', gap: 14,
          }}>
            {[
              { label: 'Shorts per video', key: 'segCount', val: segCount, min: 1, max: 8 },
              { label: 'Words per subtitle group', key: 'wordsPerGroup', val: wordsPerGroup, min: 2, max: 6 },
            ].map(({ label, key, val, min, max }) => (
              <div key={key}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: C.t2 }}>{label}</span>
                  <span style={{ fontSize: 13, fontWeight: 500, color: C.t1, fontFamily: 'monospace' }}>{val}</span>
                </div>
                <input
                  type="range"
                  min={min} max={max} step={1} value={val}
                  onChange={e => onSettingChange(key, Number(e.target.value))}
                  style={{ width: '100%', accentColor: C.teal }}
                />
              </div>
            ))}
            <div style={{
              padding: '7px 10px', background: C.panel, borderRadius: 6,
              fontSize: 11, color: C.t3, lineHeight: 1.5,
            }}>
              Active word highlighted yellow · {wordsPerGroup} words visible at once
            </div>
          </div>
        </div>

      </div>

      {/* Action */}
      <div style={{ padding: '14px 18px', borderTop: `1px solid ${C.line}` }}>
        <button
          onClick={onProcessFile}
          style={{
            width: '100%', padding: 11, borderRadius: 8, fontSize: 13, fontWeight: 500,
            background: C.tealB, border: `1px solid ${C.tealR}`, color: C.teal,
            letterSpacing: '0.02em', display: 'flex', alignItems: 'center',
            justifyContent: 'center', gap: 8, cursor: 'pointer',
          }}
        >
          ▶  Process File Now
        </button>
      </div>
    </div>
  );
}

// ── Tab Bar ───────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'queue',    label: 'Queue' },
  { id: 'segments', label: 'Segments' },
  { id: 'outputs',  label: 'Outputs' },
];

function TabBar({ active, setActive, counts }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 2, padding: '0 16px',
      borderBottom: `1px solid ${C.line}`, background: C.panel, flexShrink: 0,
    }}>
      {TABS.map(tab => (
        <button
          key={tab.id}
          onClick={() => setActive(tab.id)}
          style={{
            padding: '11px 14px', fontSize: 12, fontWeight: active === tab.id ? 500 : 400,
            background: 'transparent', color: active === tab.id ? C.teal : C.t2,
            border: 'none', borderBottom: `2px solid ${active === tab.id ? C.teal : 'transparent'}`,
            display: 'flex', alignItems: 'center', gap: 6,
            transition: 'color 0.15s', cursor: 'pointer', marginBottom: -1,
          }}
        >
          {tab.label}
          {counts[tab.id] != null && (
            <span style={{
              fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 10,
              background: active === tab.id ? C.tealB : 'rgba(255,255,255,0.06)',
              color: active === tab.id ? C.teal : C.t3,
            }}>
              {counts[tab.id]}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function ForgeShorts() {
  const [activeTab, setActiveTab]     = useState('queue');
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [watcherActive, setWatcherActive] = useState(true);

  const [settings, setSettings] = useState({
    minDur: 30, targetDur: 45, maxDur: 60,
    segCount: 4, wordsPerGroup: 4,
  });

  const [jobs, setJobs]         = useState([]);
  const [segments, setSegments] = useState([]);
  const [outputs, setOutputs]   = useState([]);
  const [loadingJobs, setLoadingJobs]         = useState(true);
  const [loadingSegments, setLoadingSegments] = useState(false);
  const [loadingOutputs, setLoadingOutputs]   = useState(false);

  // ── Fetch jobs on mount + poll every 8s ─────────────────────────
  useEffect(() => {
    const fetchJobs = async () => {
      try {
        const data = await apiFetch('/jobs');
        setJobs(data);
      } catch (err) {
        console.error('Failed to fetch jobs:', err);
      } finally {
        setLoadingJobs(false);
      }
    };
    fetchJobs();
    const interval = setInterval(fetchJobs, 8000);
    return () => clearInterval(interval);
  }, []);

  // ── Fetch segments when a job is selected ───────────────────────
  useEffect(() => {
    if (!selectedJobId) return;
    setLoadingSegments(true);
    apiFetch(`/jobs/${selectedJobId}/segments`)
      .then(setSegments)
      .catch(console.error)
      .finally(() => setLoadingSegments(false));
  }, [selectedJobId]);

  // ── Fetch all completed outputs ─────────────────────────────────
  useEffect(() => {
    if (activeTab !== 'outputs') return;
    setLoadingOutputs(true);
    apiFetch('/outputs')
      .then(setOutputs)
      .catch(console.error)
      .finally(() => setLoadingOutputs(false));
  }, [activeTab]);

  const handleSettingChange = useCallback((key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
    // Persist to backend
    apiFetch('/settings', {
      method: 'POST',
      body: JSON.stringify({ [key]: value }),
    }).catch(console.error);
  }, []);

  const handleSelectJob = useCallback((id, status) => {
    setSelectedJobId(id);
    if (status === 'complete') setActiveTab('segments');
  }, []);

  const handleProcessFile = useCallback(() => {
    // Trigger a manual file picker or call your existing process endpoint
    apiFetch('/process', { method: 'POST' }).catch(console.error);
  }, []);

  const selectedJob = jobs.find(j => j.id === selectedJobId) ?? null;
  const completedOutputs = outputs.filter(s => s.status === 'complete' && s.output_file);

  const tabCounts = {
    queue:    jobs.length,
    segments: selectedJob?.status === 'complete' ? segments.length : null,
    outputs:  completedOutputs.length || null,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* Page Header */}
      <div style={{ padding: '20px 24px 16px', borderBottom: `1px solid ${C.line}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 38, height: 38, borderRadius: 9, background: C.tealB,
            border: `1px solid ${C.tealR}`, display: 'flex', alignItems: 'center',
            justifyContent: 'center', fontSize: 16, flexShrink: 0,
          }}>
            ✂
          </div>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 600, color: C.t1, lineHeight: 1.2 }}>
              Forge Shorts
            </h1>
            <p style={{ fontSize: 12, color: C.t2, marginTop: 2 }}>
              AI-powered short-form clip extraction
            </p>
          </div>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0, overflow: 'hidden' }}>

        {/* Left: tabbed content */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
          <TabBar active={activeTab} setActive={setActiveTab} counts={tabCounts} />

          <div style={{ flex: 1, overflowY: 'auto', background: C.panel }}>
            {activeTab === 'queue' && (
              <QueuePanel
                jobs={jobs}
                selectedId={selectedJobId}
                onSelectJob={handleSelectJob}
                loading={loadingJobs}
              />
            )}
            {activeTab === 'segments' && (
              <SegmentsPanel
                job={selectedJob}
                segments={segments}
                loading={loadingSegments}
              />
            )}
            {activeTab === 'outputs' && (
              <OutputsPanel
                outputs={completedOutputs}
                loading={loadingOutputs}
              />
            )}
          </div>
        </div>

        {/* Right: settings */}
        <SettingsPanel
          watcherActive={watcherActive}
          setWatcherActive={setWatcherActive}
          settings={settings}
          onSettingChange={handleSettingChange}
          onProcessFile={handleProcessFile}
        />
      </div>
    </div>
  );
}
