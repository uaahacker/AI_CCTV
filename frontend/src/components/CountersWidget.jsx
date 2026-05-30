import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';

/**
 * Rolling counters powered by `GET /api/analytics/counters/?hours=24[&camera=]`.
 * Drop in anywhere; pass `cameraId` to scope to a single camera.
 */
export default function CountersWidget({ cameraId, hours = 24 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const params = new URLSearchParams({ hours: String(hours) });
        if (cameraId) params.set('camera', cameraId);
        const r = await api.get(`/analytics/counters/?${params.toString()}`);
        if (!cancelled) setData(r.data);
      } catch (_) {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const t = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(t); };
  }, [cameraId, hours]);

  const c = data?.counters || {};
  const p = data?.parking || {};
  const hasParking = (p.free || 0) + (p.occupied || 0) + (p.illegal || 0) > 0;

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold">Counters · last {hours}h</h2>
        {loading && <span className="text-xs text-slate-500">refreshing…</span>}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
        <Stat label="People in"     value={c.people_in}   tone="green" />
        <Stat label="People out"    value={c.people_out}  tone="slate" />
        <Stat label="Vehicles in"   value={c.vehicles_in} tone="brand" />
        <Stat label="Vehicles out"  value={c.vehicles_out} tone="slate" />
        <Stat label="Loitering"     value={c.loitering}   tone="amber" />
        <Stat label="Abandoned obj" value={c.abandoned_object} tone="red" />
      </div>

      {hasParking && (
        <>
          <div className="mt-4 mb-2 text-xs uppercase tracking-wide text-slate-500">Parking</div>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <Stat label="Free"     value={p.free}     tone="green" />
            <Stat label="Occupied" value={p.occupied} tone="brand" />
            <Stat label="Illegal"  value={p.illegal}  tone="red" />
          </div>
        </>
      )}
    </div>
  );
}

const toneClass = {
  green: 'text-green-600 dark:text-green-400',
  slate: 'text-slate-700 dark:text-slate-200',
  brand: 'text-brand-600 dark:text-brand-400',
  amber: 'text-amber-600 dark:text-amber-400',
  red:   'text-red-600 dark:text-red-400',
};

function Stat({ label, value, tone = 'slate' }) {
  return (
    <div className="rounded-md bg-slate-50 dark:bg-slate-800/60 p-3">
      <div className={`text-2xl font-semibold ${toneClass[tone] || toneClass.slate}`}>
        {value ?? 0}
      </div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}
