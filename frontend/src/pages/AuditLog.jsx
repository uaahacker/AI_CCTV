import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { fmtDate } from '../lib/format.js';

/**
 * Audit log viewer (owner / admin only).
 *
 * Backend: `GET /api/audit/logs/` supports filtering by action, user, and
 * `date_from` / `date_to` ISO timestamps. A CSV export endpoint at
 * `/api/audit/logs/export/` streams up to 10k rows respecting the same filters.
 */
export default function AuditLog() {
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [filters, setFilters] = useState({ action: '', date_from: '', date_to: '' });
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
      const { data } = await api.get(`/audit/logs/?${params.toString()}`);
      setRows(data.results || data);
      setCount(data.count ?? (data.results || data).length);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const downloadCsv = async () => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
    const { data } = await api.get(`/audit/logs/export/?${params.toString()}`, {
      responseType: 'blob',
    });
    const url = URL.createObjectURL(new Blob([data], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url; a.download = 'audit-log.csv';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Audit log</h1>
        <button onClick={downloadCsv} className="btn-secondary">Export CSV</button>
      </div>

      <div className="card p-4 grid grid-cols-1 sm:grid-cols-4 gap-3">
        <input
          className="input" placeholder="Action contains\u2026"
          value={filters.action}
          onChange={(e) => setFilters({ ...filters, action: e.target.value })}
        />
        <input
          type="datetime-local" className="input"
          value={filters.date_from}
          onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
        />
        <input
          type="datetime-local" className="input"
          value={filters.date_to}
          onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
        />
        <button onClick={load} className="btn-primary">Filter</button>
      </div>

      <div className="card p-0 overflow-hidden">
        <div className="table-scroll">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900 text-left">
              <tr>
                <th className="px-4 py-2">When</th>
                <th className="px-4 py-2">User</th>
                <th className="px-4 py-2">Action</th>
                <th className="px-4 py-2">IP</th>
                <th className="px-4 py-2">Metadata</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {loading && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-400">Loading\u2026</td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-400">No audit events.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-2 whitespace-nowrap">{fmtDate(r.created_at)}</td>
                  <td className="px-4 py-2">{r.user_email || '\u2014'}</td>
                  <td className="px-4 py-2 font-mono text-xs">{r.action}</td>
                  <td className="px-4 py-2 font-mono text-xs">{r.ip_address || ''}</td>
                  <td className="px-4 py-2 font-mono text-xs break-all max-w-md">
                    {r.metadata ? JSON.stringify(r.metadata) : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2 text-xs text-slate-500">{count} total</div>
      </div>
    </div>
  );
}
