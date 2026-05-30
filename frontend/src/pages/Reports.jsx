import { useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api.js';
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis, Legend,
} from 'recharts';

export default function Reports() {
  const [days, setDays] = useState(7);
  const [camera, setCamera] = useState('');
  const [cameras, setCameras] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [aiSummary, setAiSummary] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [aiErr, setAiErr] = useState('');

  useEffect(() => {
    api.get('/cameras/').then((r) => setCameras(r.data.results || r.data));
  }, []);

  useEffect(() => {
    setLoading(true);
    const q = new URLSearchParams({ days });
    if (camera) q.set('camera', camera);
    api.get(`/analytics/reports/?${q.toString()}`)
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, [days, camera]);

  const daily = useMemo(() =>
    (data?.daily || []).map((d) => ({
      day: d.day?.slice(0, 10),
      total: d.total || 0,
      peak: d.peak || 0,
    })), [data]);

  const hourly = useMemo(() =>
    (data?.hourly || []).map((h) => ({
      hour: h.hour?.slice(11, 16),
      total: h.total || 0,
    })), [data]);

  return (
    <div className="space-y-6">
      <div className="flex items-start sm:items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Reports</h1>
          <p className="text-sm text-slate-500">Aggregated detection analytics.</p>
        </div>
        <div className="flex flex-wrap gap-2 w-full sm:w-auto">
          <select className="input flex-1 sm:flex-initial sm:max-w-[200px]" value={camera} onChange={(e) => setCamera(e.target.value)}>
            <option value="">All cameras</option>
            {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="input flex-1 sm:flex-initial sm:max-w-[160px]" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={1}>Last 24h</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
          </select>
        </div>
      </div>

      {loading ? <div className="text-slate-500">Loading…</div> : (
        <>
          <div className="card p-5">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
              <h2 className="font-semibold">AI summary</h2>
              <button
                className="btn-secondary !py-1 !px-3 text-xs"
                disabled={aiBusy}
                onClick={async () => {
                  setAiBusy(true); setAiErr('');
                  try {
                    const q = new URLSearchParams({ days });
                    if (camera) q.set('camera', camera);
                    const r = await api.post(`/analytics/reports/ai-summary/?${q.toString()}`);
                    setAiSummary(r.data.summary || '');
                  } catch (ex) {
                    setAiErr(ex.response?.data ? JSON.stringify(ex.response.data) : 'Failed');
                  } finally {
                    setAiBusy(false);
                  }
                }}
              >
                {aiBusy ? 'Generating…' : 'Generate AI summary'}
              </button>
            </div>
            {aiSummary ? (
              <p className="text-sm whitespace-pre-line">{aiSummary}</p>
            ) : (
              <p className="text-sm text-slate-500">
                Click <em>Generate AI summary</em> to get a written brief of this period.
                If no AI provider is configured in <em>Settings → AI Settings</em>, a deterministic
                fallback summary is returned.
              </p>
            )}
            {aiErr && <p className="mt-2 text-xs text-red-600">{aiErr}</p>}
          </div>

          <div className="card p-5">
            <h2 className="font-semibold mb-3">Daily people counts</h2>
            <div style={{ width: '100%', height: 280 }}>
              <ResponsiveContainer>
                <LineChart data={daily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                  <XAxis dataKey="day" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="total" stroke="#4f6df5" strokeWidth={2} />
                  <Line type="monotone" dataKey="peak" stroke="#f59e0b" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-5">
            <h2 className="font-semibold mb-3">Hourly distribution (peak times)</h2>
            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={hourly}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                  <XAxis dataKey="hour" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="total" fill="#4f6df5" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-5">
            <h2 className="font-semibold mb-3">Per camera</h2>
            <div className="table-scroll">
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr><th className="py-2 px-2">Camera</th><th className="py-2 px-2">Total</th><th className="py-2 px-2">Peak</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {(data?.per_camera || []).map((row) => (
                  <tr key={row.camera}>
                    <td className="py-2 px-2">{row.camera__name}</td>
                    <td className="py-2 px-2">{row.total}</td>
                    <td className="py-2 px-2">{row.peak}</td>
                  </tr>
                ))}
                {(data?.per_camera || []).length === 0 && (
                  <tr><td colSpan="3" className="py-4 text-center text-slate-500">No data.</td></tr>
                )}
              </tbody>
            </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
