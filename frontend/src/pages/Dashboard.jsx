import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import StatCard from '../components/StatCard.jsx';
import LiveFeed from '../components/LiveFeed.jsx';
import CountersWidget from '../components/CountersWidget.jsx';
import { Link } from 'react-router-dom';
import { fmtDate, statusBadgeClass } from '../lib/format.js';

export default function Dashboard() {
  const [cameras, setCameras] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [camsR, alertsR, repR] = await Promise.all([
          api.get('/cameras/'),
          api.get('/alerts/'),
          api.get('/analytics/reports/?days=1'),
        ]);
        setCameras(camsR.data.results || camsR.data);
        setAlerts(alertsR.data.results || alertsR.data);
        setReport(repR.data);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const online = cameras.filter((c) => c.status === 'online').length;
  const peopleToday = (report?.daily || []).reduce((s, d) => s + (d.total || 0), 0);
  const alertsToday = alerts.filter((a) => {
    const t = new Date(a.created_at).getTime();
    return Date.now() - t < 24 * 60 * 60 * 1000;
  }).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-slate-500">Real-time overview of your fleet.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total cameras" value={cameras.length} accent="brand" />
        <StatCard label="Online" value={online} hint={`${cameras.length - online} offline`} accent="green" />
        <StatCard label="Alerts today" value={alertsToday} accent="amber" />
        <StatCard label="People counted (24h)" value={peopleToday} accent="brand" />
      </div>

      {/* Live feeds from up to 4 online cameras. Click a tile to open detail. */}
      {cameras.length > 0 && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Live feeds</h2>
            <Link to="/cameras" className="text-sm text-brand-600 hover:underline">All cameras →</Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {cameras
              .filter((c) => c.status !== 'disabled')
              .slice(0, 4)
              .map((c) => (
                <Link key={c.id} to={`/cameras/${c.id}`} className="block">
                  <LiveFeed cameraId={c.id} className="aspect-video" />
                  <div className="mt-1 flex items-center justify-between">
                    <span className="text-sm font-medium truncate">{c.name}</span>
                    <span className={statusBadgeClass(c.status)}>{c.status}</span>
                  </div>
                </Link>
              ))}
          </div>
        </div>
      )}

      <CountersWidget />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Cameras</h2>
            <Link to="/cameras" className="text-sm text-brand-600 hover:underline">Manage →</Link>
          </div>
          {loading ? <div className="text-sm text-slate-500">Loading…</div> : cameras.length === 0 ? (
            <div className="text-sm text-slate-500">No cameras yet. Add one to get started.</div>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {cameras.slice(0, 5).map((c) => (
                <li key={c.id} className="py-2 flex justify-between items-center">
                  <div>
                    <Link to={`/cameras/${c.id}`} className="font-medium hover:underline">{c.name}</Link>
                    <div className="text-xs text-slate-500">{c.location || '—'}</div>
                  </div>
                  <span className={statusBadgeClass(c.status)}>{c.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Recent alerts</h2>
            <Link to="/alerts" className="text-sm text-brand-600 hover:underline">View all →</Link>
          </div>
          {alerts.length === 0 ? (
            <div className="text-sm text-slate-500">No alerts yet.</div>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {alerts.slice(0, 5).map((a) => (
                <li key={a.id} className="py-2">
                  <div className="text-sm font-medium">{a.title}</div>
                  <div className="text-xs text-slate-500">{fmtDate(a.created_at)} · {a.severity}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
