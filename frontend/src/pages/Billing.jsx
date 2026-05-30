import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';

export default function Billing() {
  const [plans, setPlans] = useState([]);
  const [subs, setSubs] = useState([]);

  useEffect(() => {
    api.get('/billing/plans/').then((r) => setPlans(r.data.results || r.data));
    api.get('/billing/subscriptions/').then((r) => setSubs(r.data.results || r.data));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Billing</h1>
        <p className="text-sm text-slate-500">Plan management (Stripe integration coming soon).</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {plans.length === 0 && <div className="text-slate-500">No plans configured yet. Add some in Django admin.</div>}
        {plans.map((p) => (
          <div key={p.id} className="card p-6 flex flex-col">
            <div className="text-xs uppercase tracking-wide text-brand-600 font-semibold">{p.tier}</div>
            <div className="mt-1 text-2xl font-semibold">{p.name}</div>
            <div className="mt-3 text-3xl font-bold">${p.price_per_camera_monthly}<span className="text-sm font-normal text-slate-500"> / camera / mo</span></div>
            <div className="mt-2 text-sm text-slate-500">Up to {p.max_cameras} cameras</div>
            <button className="btn-primary mt-6" disabled>Choose plan</button>
          </div>
        ))}
      </div>

      {subs.length > 0 && (
        <div className="card p-5">
          <h2 className="font-semibold mb-3">Your subscriptions</h2>
          <ul className="divide-y divide-slate-200 dark:divide-slate-800 text-sm">
            {subs.map((s) => (
              <li key={s.id} className="py-2 flex justify-between">
                <span>{s.plan_detail?.name}</span>
                <span className="capitalize">{s.status}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
