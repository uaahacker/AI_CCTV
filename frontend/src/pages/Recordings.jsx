import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { fmtDate } from '../lib/format.js';

/**
 * Recording library \u2014 one row per promoted MP4 segment.
 *
 * Backend: `GET /api/cameras/recordings/` (optionally `?camera=`). Each
 * row has a `download_url` containing a short-lived HMAC token so the
 * <video> tag (or browser download) can fetch without a JWT header.
 */
export default function Recordings({ cameraId = null }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const url = cameraId
        ? `/cameras/recordings/?camera=${cameraId}`
        : '/cameras/recordings/';
      const { data } = await api.get(url);
      setRows(data.results || data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [cameraId]);

  const human = (n) => {
    if (!n) return '0 B';
    const u = ['B', 'KB', 'MB', 'GB']; let i = 0; let v = n;
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(1)} ${u[i]}`;
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">Recordings</h2>
        <button onClick={load} className="btn-secondary">Refresh</button>
      </div>

      {playing && (
        <div className="card p-3 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="font-semibold">{fmtDate(playing.started_at)}</span>
            <button onClick={() => setPlaying(null)} className="text-slate-500 hover:underline">Close</button>
          </div>
          <video src={playing.download_url} controls autoPlay
            className="w-full aspect-video bg-black rounded" />
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="table-scroll">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900 text-left">
              <tr>
                <th className="px-4 py-2">Started</th>
                <th className="px-4 py-2">Kind</th>
                <th className="px-4 py-2">Duration</th>
                <th className="px-4 py-2">Size</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {loading && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-400">Loading\u2026</td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                  No recordings yet. Enable continuous recording on a camera.
                </td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-2 whitespace-nowrap">{fmtDate(r.started_at)}</td>
                  <td className="px-4 py-2 capitalize">{r.kind}</td>
                  <td className="px-4 py-2">{r.duration_s}s</td>
                  <td className="px-4 py-2">{human(r.size_bytes)}</td>
                  <td className="px-4 py-2 text-right space-x-3">
                    <button onClick={() => setPlaying(r)} className="text-brand-600 hover:underline">Play</button>
                    <a href={r.download_url} download className="text-brand-600 hover:underline">Download</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
