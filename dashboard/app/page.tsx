"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  login as apiLogin,
  getMe,
  getAnalyticsSummary,
  getAnalyticsRequests,
  getAnalyticsUsers,
  getAuditLogs,
  getPolicies,
  createPolicy,
  deletePolicy,
  getRateLimits,
  createRateLimit,
  deleteRateLimit,
  getGuardrails,
  createGuardrail,
  deleteGuardrail,
  getGatewayConfig,
  sendPrompt,
} from "@/lib/api";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area,
} from "recharts";

/* ─── Types ──────────────────────────────────────────────────────────────── */
interface Summary {
  total_requests: number;
  total_tokens: number;
  total_cost_usd: number;
  total_users: number;
  cache_hit_rate: number;
  avg_latency_ms: number;
  model_usage: Record<string, number>;
  provider_usage: Record<string, number>;
}

interface RequestLog {
  id: number;
  username: string;
  model: string;
  provider: string;
  tokens_used: number;
  cost_usd: number;
  cache_hit: boolean;
  latency_ms: number;
  created_at: string;
  prompt_preview: string;
  response_preview: string;
}

/* ─── Constants ──────────────────────────────────────────────────────────── */
const CHART_COLORS = ["#4f8cff", "#a855f7", "#34d399", "#fbbf24", "#fb7185", "#22d3ee"];

const PAGES = [
  { id: "dashboard", label: "Dashboard", icon: "📊", section: "Analytics" },
  { id: "requests", label: "Request Explorer", icon: "🔍", section: "Analytics" },
  { id: "users", label: "User Management", icon: "👥", section: "Admin" },
  { id: "policies", label: "Policy Manager", icon: "🛡️", section: "Admin" },
  { id: "rate-limits", label: "Rate Limits", icon: "⏱️", section: "Admin" },
  { id: "guardrails", label: "Guardrails", icon: "🚧", section: "Admin" },
  { id: "playground", label: "Playground", icon: "🧪", section: "Tools" },
];

/* ═══════════════════════════════════════════════════════════════════════════
   LOGIN SCREEN
   ═══════════════════════════════════════════════════════════════════════════ */

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiLogin(username, password);
      onLogin();
    } catch {
      setError("Invalid credentials. Try admin/admin123");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <div className="sidebar-logo-icon" style={{ width: 48, height: 48, fontSize: 22, margin: "0 auto 12px", borderRadius: 12 }}>⚡</div>
        </div>
        <h1 className="login-title">AI Gateway</h1>
        <p className="login-subtitle">Enterprise LLM Control Plane</p>
        {error && <div className="login-error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="input-group">
            <label className="input-label">Username</label>
            <input className="input" type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin" autoFocus />
          </div>
          <div className="input-group">
            <label className="input-label">Password</label>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••" />
          </div>
          <button className="btn btn-primary" type="submit" style={{ width: "100%", justifyContent: "center", marginTop: 8 }} disabled={loading}>
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
        <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", marginTop: 16 }}>
          Default: admin / admin123
        </p>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   DASHBOARD PAGE (KPIs + Charts)
   ═══════════════════════════════════════════════════════════════════════════ */

function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    getAnalyticsSummary().then(setSummary).catch(console.error);
  }, []);

  if (!summary) return <LoadingState />;

  const modelData = Object.entries(summary.model_usage).map(([name, value]) => ({ name, value }));
  const providerData = Object.entries(summary.provider_usage).map(([name, value]) => ({ name, value }));

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Real-time overview of your AI Gateway</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card blue">
          <div className="kpi-icon blue">📡</div>
          <div className="kpi-label">Total Requests</div>
          <div className="kpi-value">{summary.total_requests.toLocaleString()}</div>
        </div>
        <div className="kpi-card purple">
          <div className="kpi-icon purple">🔤</div>
          <div className="kpi-label">Total Tokens</div>
          <div className="kpi-value">{summary.total_tokens.toLocaleString()}</div>
        </div>
        <div className="kpi-card emerald">
          <div className="kpi-icon emerald">💰</div>
          <div className="kpi-label">Total Cost</div>
          <div className="kpi-value">${summary.total_cost_usd.toFixed(4)}</div>
        </div>
        <div className="kpi-card amber">
          <div className="kpi-icon amber">👤</div>
          <div className="kpi-label">Active Users</div>
          <div className="kpi-value">{summary.total_users}</div>
        </div>
        <div className="kpi-card cyan">
          <div className="kpi-icon cyan">⚡</div>
          <div className="kpi-label">Cache Hit Rate</div>
          <div className="kpi-value">{summary.cache_hit_rate}%</div>
        </div>
        <div className="kpi-card rose">
          <div className="kpi-icon rose">⏱️</div>
          <div className="kpi-label">Avg Latency</div>
          <div className="kpi-value">{summary.avg_latency_ms}ms</div>
        </div>
      </div>

      <div className="charts-grid-equal">
        <div className="card">
          <div className="card-header"><span className="card-title">Model Usage</span></div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={modelData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="name" tick={{ fill: "#8b8ba3", fontSize: 11 }} />
              <YAxis tick={{ fill: "#8b8ba3", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: "#16161f", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#f0f0f5" }}
              />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {modelData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Provider Distribution</span></div>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={providerData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" label={({ name, percent }: { name: string; percent: number }) => `${name} (${(percent * 100).toFixed(0)}%)`}>
                {providerData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: "#16161f", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   REQUEST EXPLORER
   ═══════════════════════════════════════════════════════════════════════════ */

function RequestExplorerPage() {
  const [requests, setRequests] = useState<RequestLog[]>([]);
  const [selected, setSelected] = useState<RequestLog | null>(null);

  useEffect(() => {
    getAnalyticsRequests(100).then(setRequests).catch(console.error);
  }, []);

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Request Explorer</h1>
        <p className="page-subtitle">Browse and inspect all gateway requests</p>
      </div>

      <div className="card">
        <div className="data-table-container" style={{ maxHeight: "70vh", overflowY: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>User</th>
                <th>Model</th>
                <th>Provider</th>
                <th>Tokens</th>
                <th>Cost</th>
                <th>Latency</th>
                <th>Cache</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id} onClick={() => setSelected(r)} style={{ cursor: "pointer" }}>
                  <td style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>#{r.id}</td>
                  <td style={{ color: "var(--text-primary)", fontWeight: 500 }}>{r.username}</td>
                  <td><span className="badge blue">{r.model}</span></td>
                  <td><span className="badge purple">{r.provider}</span></td>
                  <td>{r.tokens_used?.toLocaleString()}</td>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>${r.cost_usd?.toFixed(6)}</td>
                  <td>{r.latency_ms}ms</td>
                  <td>{r.cache_hit ? <span className="badge emerald">HIT</span> : <span className="badge rose">MISS</span>}</td>
                  <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{r.created_at ? new Date(r.created_at).toLocaleString() : "-"}</td>
                </tr>
              ))}
              {requests.length === 0 && (
                <tr><td colSpan={9} style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}>No requests yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal-title">Request #{selected.id}</h2>
            <div className="input-group">
              <label className="input-label">Prompt Preview</label>
              <div style={{ background: "var(--bg-input)", padding: 12, borderRadius: 8, fontSize: 13, color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
                {selected.prompt_preview || "—"}
              </div>
            </div>
            <div className="input-group">
              <label className="input-label">Response Preview</label>
              <div style={{ background: "var(--bg-input)", padding: 12, borderRadius: 8, fontSize: 13, color: "var(--text-secondary)", whiteSpace: "pre-wrap", maxHeight: 200, overflowY: "auto" }}>
                {selected.response_preview || "—"}
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
              <div><span className="input-label">Model</span><div style={{ fontSize: 14 }}>{selected.model}</div></div>
              <div><span className="input-label">Provider</span><div style={{ fontSize: 14 }}>{selected.provider}</div></div>
              <div><span className="input-label">Tokens</span><div style={{ fontSize: 14 }}>{selected.tokens_used}</div></div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setSelected(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   USER MANAGEMENT
   ═══════════════════════════════════════════════════════════════════════════ */

function UsersPage() {
  const [users, setUsers] = useState<any[]>([]);

  useEffect(() => {
    getAnalyticsUsers().then(setUsers).catch(console.error);
  }, []);

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">User Management</h1>
        <p className="page-subtitle">View user activity and manage access</p>
      </div>
      <div className="card">
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Full Name</th>
                <th>Role</th>
                <th>Department</th>
                <th>Requests</th>
                <th>Tokens Used</th>
                <th>Total Cost</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td style={{ color: "var(--text-primary)", fontWeight: 600 }}>{u.username}</td>
                  <td>{u.full_name || "—"}</td>
                  <td><span className={`badge ${u.role === "admin" ? "amber" : "blue"}`}>{u.role}</span></td>
                  <td>{u.department || "—"}</td>
                  <td>{u.total_requests}</td>
                  <td>{u.total_tokens?.toLocaleString()}</td>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>${u.total_cost_usd?.toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   POLICY MANAGER
   ═══════════════════════════════════════════════════════════════════════════ */

function PoliciesPage() {
  const [policies, setPolicies] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ effect: "deny", resource: "prompt", action: "create", target_role: "", target_department: "" });

  const load = () => getPolicies().then(setPolicies).catch(console.error);
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    await createPolicy({ ...form, target_role: form.target_role || null, target_department: form.target_department || null });
    setShowCreate(false);
    load();
  };

  const handleDelete = async (id: number) => {
    await deletePolicy(id);
    load();
  };

  return (
    <>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 className="page-title">Policy Manager</h1>
          <p className="page-subtitle">Control access with allow/deny rules</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ Create Policy</button>
      </div>

      <div className="card">
        <div className="data-table-container">
          <table className="data-table">
            <thead><tr><th>ID</th><th>Effect</th><th>Resource</th><th>Action</th><th>Target Role</th><th>Target Dept.</th><th></th></tr></thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.id}>
                  <td>#{p.id}</td>
                  <td><span className={`badge ${p.effect === "deny" ? "rose" : "emerald"}`}>{p.effect.toUpperCase()}</span></td>
                  <td>{p.resource || "*"}</td>
                  <td>{p.action || "*"}</td>
                  <td>{p.target_role || "all"}</td>
                  <td>{p.target_department || "all"}</td>
                  <td><button className="btn btn-danger btn-sm" onClick={() => handleDelete(p.id)}>Delete</button></td>
                </tr>
              ))}
              {policies.length === 0 && <tr><td colSpan={7} style={{ textAlign: "center", padding: 32, color: "var(--text-muted)" }}>No policies configured — all requests allowed by default</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal-title">Create Policy Rule</h2>
            <div className="input-group">
              <label className="input-label">Effect</label>
              <select className="input" value={form.effect} onChange={(e) => setForm({ ...form, effect: e.target.value })}>
                <option value="deny">Deny</option><option value="allow">Allow</option>
              </select>
            </div>
            <div className="input-group"><label className="input-label">Resource</label><input className="input" value={form.resource} onChange={(e) => setForm({ ...form, resource: e.target.value })} placeholder="prompt" /></div>
            <div className="input-group"><label className="input-label">Action</label><input className="input" value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })} placeholder="create" /></div>
            <div className="input-group"><label className="input-label">Target Role (optional)</label><input className="input" value={form.target_role} onChange={(e) => setForm({ ...form, target_role: e.target.value })} placeholder="user" /></div>
            <div className="input-group"><label className="input-label">Target Department (optional)</label><input className="input" value={form.target_department} onChange={(e) => setForm({ ...form, target_department: e.target.value })} /></div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate}>Create</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   RATE LIMITS
   ═══════════════════════════════════════════════════════════════════════════ */

function RateLimitsPage() {
  const [limits, setLimits] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ scope: "user", target: "", window: "hour", max_tokens: "", max_requests: "" });

  const load = () => getRateLimits().then(setLimits).catch(console.error);
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    await createRateLimit({
      scope: form.scope,
      target: form.target || null,
      window: form.window,
      max_tokens: form.max_tokens ? parseInt(form.max_tokens) : null,
      max_requests: form.max_requests ? parseInt(form.max_requests) : null,
    });
    setShowCreate(false);
    load();
  };

  return (
    <>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div><h1 className="page-title">Rate Limits</h1><p className="page-subtitle">Configure token and request budgets</p></div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ Create Limit</button>
      </div>
      <div className="card">
        <div className="data-table-container">
          <table className="data-table">
            <thead><tr><th>ID</th><th>Scope</th><th>Target</th><th>Window</th><th>Max Tokens</th><th>Max Requests</th><th></th></tr></thead>
            <tbody>
              {limits.map((l) => (
                <tr key={l.id}>
                  <td>#{l.id}</td>
                  <td><span className={`badge ${l.scope === "global" ? "amber" : l.scope === "department" ? "purple" : "blue"}`}>{l.scope}</span></td>
                  <td>{l.target || "all"}</td>
                  <td>{l.window}</td>
                  <td>{l.max_tokens?.toLocaleString() || "∞"}</td>
                  <td>{l.max_requests?.toLocaleString() || "∞"}</td>
                  <td><button className="btn btn-danger btn-sm" onClick={() => { deleteRateLimit(l.id).then(load); }}>Delete</button></td>
                </tr>
              ))}
              {limits.length === 0 && <tr><td colSpan={7} style={{ textAlign: "center", padding: 32, color: "var(--text-muted)" }}>No rate limits — all requests unlimited</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal-title">Create Rate Limit</h2>
            <div className="input-group">
              <label className="input-label">Scope</label>
              <select className="input" value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>
                <option value="user">Per User</option><option value="department">Per Department</option><option value="global">Global</option>
              </select>
            </div>
            <div className="input-group"><label className="input-label">Target (username or dept name)</label><input className="input" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} /></div>
            <div className="input-group">
              <label className="input-label">Window</label>
              <select className="input" value={form.window} onChange={(e) => setForm({ ...form, window: e.target.value })}>
                <option value="minute">Per Minute</option><option value="hour">Per Hour</option><option value="day">Per Day</option>
              </select>
            </div>
            <div className="input-group"><label className="input-label">Max Tokens</label><input className="input" type="number" value={form.max_tokens} onChange={(e) => setForm({ ...form, max_tokens: e.target.value })} placeholder="50000" /></div>
            <div className="input-group"><label className="input-label">Max Requests</label><input className="input" type="number" value={form.max_requests} onChange={(e) => setForm({ ...form, max_requests: e.target.value })} placeholder="100" /></div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate}>Create</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   GUARDRAILS
   ═══════════════════════════════════════════════════════════════════════════ */

function GuardrailsPage() {
  const [guardrails, setGuardrails] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", stage: "pre", check_type: "max_length", config_json: '{"max_characters": 10000}', action: "block", target_model: "", target_department: "" });

  const load = () => getGuardrails().then(setGuardrails).catch(console.error);
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    await createGuardrail({ ...form, target_model: form.target_model || null, target_department: form.target_department || null });
    setShowCreate(false);
    load();
  };

  return (
    <>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div><h1 className="page-title">Guardrails</h1><p className="page-subtitle">Input validation and output quality controls</p></div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ Create Guardrail</button>
      </div>
      <div className="card">
        <div className="data-table-container">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Stage</th><th>Check Type</th><th>Action</th><th>Model</th><th>Active</th><th></th></tr></thead>
            <tbody>
              {guardrails.map((g) => (
                <tr key={g.id}>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{g.name}</td>
                  <td><span className={`badge ${g.stage === "pre" ? "blue" : "purple"}`}>{g.stage === "pre" ? "Pre-Request" : "Post-Response"}</span></td>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{g.check_type}</td>
                  <td><span className={`badge ${g.action === "block" ? "rose" : "amber"}`}>{g.action}</span></td>
                  <td>{g.target_model || "all"}</td>
                  <td>{g.is_active ? <span className="badge emerald">Active</span> : <span className="badge rose">Inactive</span>}</td>
                  <td><button className="btn btn-danger btn-sm" onClick={() => { deleteGuardrail(g.id).then(load); }}>Delete</button></td>
                </tr>
              ))}
              {guardrails.length === 0 && <tr><td colSpan={7} style={{ textAlign: "center", padding: 32, color: "var(--text-muted)" }}>No guardrails configured</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal-title">Create Guardrail</h2>
            <div className="input-group"><label className="input-label">Name</label><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Block long prompts" /></div>
            <div className="input-group">
              <label className="input-label">Stage</label>
              <select className="input" value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })}>
                <option value="pre">Pre-Request (Input)</option><option value="post">Post-Response (Output)</option>
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">Check Type</label>
              <select className="input" value={form.check_type} onChange={(e) => setForm({ ...form, check_type: e.target.value })}>
                <option value="max_length">Max Length</option><option value="prohibited_topics">Prohibited Topics</option><option value="regex_filter">Regex Filter</option><option value="json_output">JSON Output</option><option value="min_length">Min Length</option>
              </select>
            </div>
            <div className="input-group"><label className="input-label">Config (JSON)</label><textarea className="input" value={form.config_json} onChange={(e) => setForm({ ...form, config_json: e.target.value })} /></div>
            <div className="input-group">
              <label className="input-label">Action</label>
              <select className="input" value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })}>
                <option value="block">Block</option><option value="warn">Warn</option>
              </select>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate}>Create</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   PLAYGROUND
   ═══════════════════════════════════════════════════════════════════════════ */

function PlaygroundPage() {
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("gpt-4o-mini");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    try {
      const res = await sendPrompt(prompt, model);
      setResult(res);
    } catch (e) {
      setResult({ error: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Playground</h1>
        <p className="page-subtitle">Test prompts through the gateway pipeline</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card">
          <div className="card-header"><span className="card-title">Input</span></div>
          <div className="input-group">
            <label className="input-label">Model</label>
            <select className="input" value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="gpt-4o-mini">GPT-4o Mini</option>
              <option value="gpt-4o">GPT-4o</option>
              <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
              <option value="claude-sonnet-4">Claude Sonnet 4</option>
              <option value="gemini-2.0-flash">Gemini 2.0 Flash</option>
            </select>
          </div>
          <div className="input-group">
            <label className="input-label">Prompt</label>
            <textarea className="input" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Enter your prompt..." style={{ minHeight: 200 }} />
          </div>
          <button className="btn btn-primary" onClick={handleSend} disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
            {loading ? "Processing..." : "Send Prompt"}
          </button>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Response</span></div>
          {result ? (
            <>
              {result.error ? (
                <div className="login-error">{result.error}</div>
              ) : (
                <>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
                    <div className="kpi-card blue" style={{ padding: 12 }}>
                      <div className="kpi-label" style={{ fontSize: 10 }}>Provider</div>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>{result.provider}</div>
                    </div>
                    <div className="kpi-card purple" style={{ padding: 12 }}>
                      <div className="kpi-label" style={{ fontSize: 10 }}>Tokens</div>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>{result.tokens_used}</div>
                    </div>
                    <div className="kpi-card emerald" style={{ padding: 12 }}>
                      <div className="kpi-label" style={{ fontSize: 10 }}>Cost</div>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>${result.cost_usd?.toFixed(6)}</div>
                    </div>
                  </div>
                  <div className="input-group">
                    <label className="input-label">Masked Prompt</label>
                    <div style={{ background: "var(--bg-input)", padding: 12, borderRadius: 8, fontSize: 13, color: "var(--accent-amber)" }}>{result.masked_prompt}</div>
                  </div>
                  <div className="input-group">
                    <label className="input-label">LLM Response</label>
                    <div style={{ background: "var(--bg-input)", padding: 12, borderRadius: 8, fontSize: 13, color: "var(--text-secondary)", maxHeight: 300, overflowY: "auto", whiteSpace: "pre-wrap" }}>{result.llm_response}</div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    {result.cache_hit && <span className="badge emerald">Cache Hit</span>}
                    <span className="badge blue">{result.latency_ms}ms</span>
                  </div>
                </>
              )}
            </>
          ) : (
            <div style={{ color: "var(--text-muted)", textAlign: "center", padding: 60 }}>Send a prompt to see the response</div>
          )}
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   LOADING STATE
   ═══════════════════════════════════════════════════════════════════════════ */

function LoadingState() {
  return (
    <div className="kpi-grid">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="skeleton" style={{ height: 110, borderRadius: 16 }} />
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN APP
   ═══════════════════════════════════════════════════════════════════════════ */

export default function Home() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [activePage, setActivePage] = useState("dashboard");
  const [username, setUsername] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("token");
    const user = localStorage.getItem("username");
    if (token && user) {
      setLoggedIn(true);
      setUsername(user);
    }
  }, []);

  if (!loggedIn) {
    return (
      <LoginScreen
        onLogin={() => {
          setLoggedIn(true);
          setUsername(localStorage.getItem("username") || "");
        }}
      />
    );
  }

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    setLoggedIn(false);
  };

  const renderPage = () => {
    switch (activePage) {
      case "dashboard": return <DashboardPage />;
      case "requests": return <RequestExplorerPage />;
      case "users": return <UsersPage />;
      case "policies": return <PoliciesPage />;
      case "rate-limits": return <RateLimitsPage />;
      case "guardrails": return <GuardrailsPage />;
      case "playground": return <PlaygroundPage />;
      default: return <DashboardPage />;
    }
  };

  // Group pages by section
  const sections = PAGES.reduce((acc, page) => {
    if (!acc[page.section]) acc[page.section] = [];
    acc[page.section].push(page);
    return acc;
  }, {} as Record<string, typeof PAGES>);

  return (
    <div className="app-layout">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">⚡</div>
            <div>
              <div className="sidebar-logo-text">AI Gateway</div>
              <div className="sidebar-logo-version">v2.0 Enterprise</div>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {Object.entries(sections).map(([section, pages]) => (
            <div key={section}>
              <div className="nav-section-label">{section}</div>
              {pages.map((page) => (
                <div
                  key={page.id}
                  className={`nav-item ${activePage === page.id ? "active" : ""}`}
                  onClick={() => setActivePage(page.id)}
                >
                  <span className="nav-item-icon">{page.icon}</span>
                  {page.label}
                </div>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{username}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Admin</div>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={handleLogout}>Logout</button>
          </div>
        </div>
      </aside>

      {/* ── Main Content ── */}
      <main className="main-content">
        {renderPage()}
      </main>
    </div>
  );
}
