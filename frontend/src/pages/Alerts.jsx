import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { fmtDate, severityBadgeClass } from '../lib/format.js';

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const r = await api.get('/alerts/');
    setAlerts(r.data.results || r.data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const updateStatus = async (id, status) => {
    await api.patch(`/alerts/${id}/`, { status });
    load();
  };

  const filtered = filter === 'all' ? alerts : alerts.filter((a) => a.status === filter);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Alerts</h1>
          <p className="text-sm text-slate-500">Triggered events from your rules engine.</p>
        </div>
        <select className="input max-w-[160px]" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All</option>
          <option value="new">New</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
        </select>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">When</th>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Severity</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {loading ? (
              <tr><td colSpan="5" className="px-4 py-8 text-center text-slate-500">Loading…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan="5" className="px-4 py-8 text-center text-slate-500">No alerts.</td></tr>
            ) : filtered.map((a) => (
              <tr key={a.id}>
                <td className="px-4 py-3 text-slate-500 text-xs">{fmtDate(a.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="font-medium">{a.title}</div>
                  <div className="text-xs text-slate-500">{a.message}</div>
                  {a.ai_summary && (
                    <div className="mt-1 text-xs italic text-slate-500 border-l-2 border-brand-400 pl-2">
                      AI: {a.ai_summary}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3"><span className={severityBadgeClass(a.severity)}>{a.severity}</span></td>
                <td className="px-4 py-3 capitalize">{a.status}</td>
                <td className="px-4 py-3 text-right space-x-2">
                  {a.status !== 'acknowledged' && (
                    <button onClick={() => updateStatus(a.id, 'acknowledged')} className="btn-secondary !py-1 !px-2 text-xs">Ack</button>
                  )}
                  {a.status !== 'resolved' && (
                    <button onClick={() => updateStatus(a.id, 'resolved')} className="btn-primary !py-1 !px-2 text-xs">Resolve</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
