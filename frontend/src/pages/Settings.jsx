import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { fmtDate } from '../lib/format.js';

export default function Settings() {
  const { user } = useAuth();
  const [orgs, setOrgs] = useState([]);
  const [name, setName] = useState('');
  const [err, setErr] = useState('');

  const load = async () => {
    const r = await api.get('/organizations/');
    setOrgs(r.data.results || r.data);
  };
  useEffect(() => { load(); }, []);

  const createOrg = async (e) => {
    e.preventDefault();
    setErr('');
    try {
      await api.post('/organizations/', { name });
      setName('');
      load();
    } catch (ex) {
      setErr(ex.response?.data ? JSON.stringify(ex.response.data) : 'Failed');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-slate-500">Profile and organization management.</p>
      </div>

      <div className="card p-5">
        <h2 className="font-semibold mb-3">Profile</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <div><div className="text-slate-500">Email</div><div>{user?.email}</div></div>
          <div><div className="text-slate-500">Full name</div><div>{user?.full_name || '—'}</div></div>
          <div><div className="text-slate-500">Joined</div><div>{fmtDate(user?.date_joined)}</div></div>
        </div>
      </div>

      <div className="card p-5">
        <h2 className="font-semibold mb-3">Organizations</h2>
        <ul className="divide-y divide-slate-200 dark:divide-slate-800 text-sm">
          {orgs.length === 0 && <li className="py-2 text-slate-500">You aren't a member of any organization yet.</li>}
          {orgs.map((o) => (
            <li key={o.id} className="py-2 flex justify-between">
              <div>
                <div className="font-medium">{o.name}</div>
                <div className="text-xs text-slate-500">{o.slug}</div>
              </div>
              <span className="badge-gray capitalize">{o.role || 'member'}</span>
            </li>
          ))}
        </ul>
        <form onSubmit={createOrg} className="mt-4 flex flex-col sm:flex-row gap-2">
          <input className="input" placeholder="New organization name" value={name} onChange={(e) => setName(e.target.value)} required />
          <button className="btn-primary shrink-0">Create</button>
        </form>
        {err && <div className="mt-2 text-sm text-red-600">{err}</div>}
      </div>
    </div>
  );
}
