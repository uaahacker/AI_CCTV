import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../lib/api.js';
import { fmtDate, statusBadgeClass } from '../lib/format.js';
import LiveFeed from '../components/LiveFeed.jsx';
import CountersWidget from '../components/CountersWidget.jsx';

export default function CameraDetail() {
  const { id } = useParams();
  const [cam, setCam] = useState(null);
  const [events, setEvents] = useState([]);
  const [checks, setChecks] = useState([]);

  const load = async () => {
    const [c, ev, hc] = await Promise.all([
      api.get(`/cameras/${id}/`),
      api.get(`/analytics/events/?camera=${id}`),
      api.get(`/cameras/health-checks/?camera=${id}`),
    ]);
    setCam(c.data);
    setEvents(ev.data.results || ev.data);
    setChecks(hc.data.results || hc.data);
  };
  useEffect(() => { load(); }, [id]);

  if (!cam) return <div className="text-slate-500">Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-start sm:items-center justify-between flex-wrap gap-3">
        <div className="min-w-0">
          <Link to="/cameras" className="text-sm text-brand-600 hover:underline">← Cameras</Link>
          <h1 className="text-2xl font-semibold mt-1 truncate">{cam.name}</h1>
          <p className="text-sm text-slate-500">{cam.location || 'No location'}</p>
        </div>
        <span className={statusBadgeClass(cam.status)}>{cam.status}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <LiveFeed cameraId={id} className="aspect-video w-full" />
        </div>
        <div>
          <CountersWidget cameraId={id} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-4">
          <div className="text-xs text-slate-500">RTSP</div>
          <div className="font-mono text-xs break-all mt-1">{cam.rtsp_url_masked}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-slate-500">Last seen</div>
          <div className="mt-1">{fmtDate(cam.last_seen_at)}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-slate-500">Last error</div>
          <div className="mt-1 text-sm break-words">{cam.last_error || '—'}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-5">
          <h2 className="font-semibold mb-3">Recent detections</h2>
          {events.length === 0 ? (
            <div className="text-sm text-slate-500">No events yet. Start the CV worker to populate.</div>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800 text-sm">
              {events.slice(0, 10).map((e) => (
                <li key={e.id} className="py-2 flex justify-between">
                  <span>{e.event_type} · <span className="font-medium">{e.people_count}</span></span>
                  <span className="text-slate-500 text-xs">{fmtDate(e.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card p-5">
          <h2 className="font-semibold mb-3">Health checks</h2>
          {checks.length === 0 ? (
            <div className="text-sm text-slate-500">No checks yet.</div>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800 text-sm">
              {checks.slice(0, 10).map((h) => (
                <li key={h.id} className="py-2 flex justify-between">
                  <span><span className={statusBadgeClass(h.status)}>{h.status}</span> {h.latency_ms ? `· ${h.latency_ms}ms` : ''}</span>
                  <span className="text-slate-500 text-xs">{fmtDate(h.checked_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
