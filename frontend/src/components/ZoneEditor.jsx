import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api.js';

/**
 * Zone editor \u2014 an SVG overlay on the live feed for drawing polygon, line
 * (tripwire) and parking-slot zones. All coordinates are normalised to
 * [0,1] so they remain valid across resolution changes.
 *
 * Usage:
 *   <ZoneEditor cameraId={id} onSaved={refresh} />
 *
 * Backend contract: `POST /api/cameras/zones/` with
 *   { camera, name, kind, geometry: [[x,y],...], direction?, config? }
 */
export default function ZoneEditor({ cameraId, onSaved }) {
  const svgRef = useRef(null);
  const [zones, setZones] = useState([]);
  const [draft, setDraft] = useState({ kind: 'polygon', name: '', direction: 'both', points: [] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadZones = async () => {
    const { data } = await api.get(`/cameras/zones/?camera=${cameraId}`);
    setZones(data.results || data);
  };
  useEffect(() => { loadZones(); /* eslint-disable-next-line */ }, [cameraId]);

  const onClick = (e) => {
    const rect = svgRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const clamped = [Math.max(0, Math.min(1, x)), Math.max(0, Math.min(1, y))];
    // Lines max out at 2 points.
    if (draft.kind === 'line' && draft.points.length >= 2) return;
    setDraft({ ...draft, points: [...draft.points, clamped] });
  };

  const undo = () => setDraft({ ...draft, points: draft.points.slice(0, -1) });
  const clear = () => setDraft({ ...draft, points: [] });

  const save = async () => {
    setError('');
    if (!draft.name) { setError('Name required'); return; }
    if (draft.kind === 'line' && draft.points.length !== 2) {
      setError('A line requires exactly 2 points'); return;
    }
    if (draft.kind !== 'line' && draft.points.length < 3) {
      setError('Polygon / parking slot needs at least 3 points'); return;
    }
    setBusy(true);
    try {
      await api.post('/cameras/zones/', {
        camera: cameraId,
        name: draft.name,
        kind: draft.kind,
        geometry: draft.points,
        direction: draft.kind === 'line' ? draft.direction : 'none',
      });
      setDraft({ kind: draft.kind, name: '', direction: 'both', points: [] });
      await loadZones();
      onSaved && onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not save zone');
    } finally {
      setBusy(false);
    }
  };

  const deleteZone = async (id) => {
    if (!confirm('Delete this zone?')) return;
    await api.delete(`/cameras/zones/${id}/`);
    loadZones();
  };

  const W = 100, H = 100;  // virtual SVG units \u2014 actual scale handled by viewBox

  return (
    <div className="space-y-3">
      <div
        className="relative w-full aspect-video bg-slate-900 rounded overflow-hidden border border-slate-700"
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          onClick={onClick}
          className="absolute inset-0 w-full h-full cursor-crosshair"
        >
          {/* existing zones, dimmed */}
          {zones.map((z) => {
            const pts = (z.geometry || []).map(([x, y]) => `${x * W},${y * H}`).join(' ');
            const stroke = z.kind === 'line' ? '#facc15'
              : z.kind === 'parking_slot' ? '#60a5fa' : '#34d399';
            return z.kind === 'line' ? (
              <polyline key={z.id} points={pts} stroke={stroke} strokeWidth="0.5" fill="none" opacity="0.5" />
            ) : (
              <polygon key={z.id} points={pts} stroke={stroke} strokeWidth="0.3" fill={stroke} fillOpacity="0.12" />
            );
          })}
          {/* draft */}
          {draft.points.length > 0 && (
            draft.kind === 'line' ? (
              <polyline
                points={draft.points.map(([x, y]) => `${x * W},${y * H}`).join(' ')}
                stroke="#f87171" strokeWidth="0.6" fill="none" strokeDasharray="1,0.5"
              />
            ) : (
              <polygon
                points={draft.points.map(([x, y]) => `${x * W},${y * H}`).join(' ')}
                stroke="#f87171" strokeWidth="0.4" fill="#f87171" fillOpacity="0.2"
              />
            )
          )}
          {draft.points.map(([x, y], i) => (
            <circle key={i} cx={x * W} cy={y * H} r="0.6" fill="#f87171" />
          ))}
        </svg>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
        <select className="input" value={draft.kind}
          onChange={(e) => setDraft({ ...draft, kind: e.target.value, points: [] })}>
          <option value="polygon">Polygon (region)</option>
          <option value="line">Line (tripwire)</option>
          <option value="parking_slot">Parking slot</option>
        </select>
        <input className="input sm:col-span-2" placeholder="Zone name"
          value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        {draft.kind === 'line' ? (
          <select className="input" value={draft.direction}
            onChange={(e) => setDraft({ ...draft, direction: e.target.value })}>
            <option value="both">Count both directions</option>
            <option value="in">Count IN only</option>
            <option value="out">Count OUT only</option>
            <option value="none">Bi-directional (no count)</option>
          </select>
        ) : <div />}
      </div>

      <div className="flex flex-wrap gap-2">
        <button onClick={undo} className="btn-secondary" disabled={!draft.points.length}>Undo point</button>
        <button onClick={clear} className="btn-secondary" disabled={!draft.points.length}>Clear</button>
        <button onClick={save} className="btn-primary" disabled={busy}>
          {busy ? 'Saving\u2026' : 'Save zone'}
        </button>
        <span className="text-xs text-slate-500 self-center">
          {draft.points.length} point{draft.points.length === 1 ? '' : 's'} placed
        </span>
      </div>
      {error && <div className="text-sm text-red-600">{error}</div>}

      {zones.length > 0 && (
        <div className="card p-3">
          <div className="text-xs font-semibold mb-2 text-slate-500">Existing zones</div>
          <ul className="divide-y divide-slate-200 dark:divide-slate-800 text-sm">
            {zones.map((z) => (
              <li key={z.id} className="py-2 flex justify-between items-center">
                <span>
                  <span className="font-medium">{z.name}</span>
                  <span className="text-slate-500 text-xs"> \u00b7 {z.kind}
                    {z.kind === 'line' && z.direction !== 'none' ? ` \u00b7 ${z.direction}` : ''}
                  </span>
                </span>
                <button onClick={() => deleteZone(z.id)}
                  className="text-xs text-red-600 hover:underline">Delete</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
