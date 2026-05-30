import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import Modal from '../components/Modal.jsx';
import { fmtDate } from '../lib/format.js';

const empty = {
  organization: '',
  camera: '',
  name: '',
  rule_type: 'people_count',
  threshold_value: 10,
  condition: 'greater_than',
  notification_email: '',
  cooldown_seconds: 300,
  is_active: true,
};

export default function AlertRules() {
  const [rules, setRules] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(empty);
  const [err, setErr] = useState('');
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    const [r, o, c] = await Promise.all([
      api.get('/alerts/rules/'),
      api.get('/organizations/'),
      api.get('/cameras/'),
    ]);
    setRules(r.data.results || r.data);
    setOrgs(o.data.results || o.data);
    setCameras(c.data.results || c.data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...empty, organization: orgs[0]?.id || '' });
    setErr('');
    setOpen(true);
  };

  const openEdit = (rule) => {
    setEditing(rule);
    setForm({
      organization: rule.organization,
      camera: rule.camera || '',
      name: rule.name,
      rule_type: rule.rule_type,
      threshold_value: rule.threshold_value,
      condition: rule.condition,
      notification_email: rule.notification_email || '',
      cooldown_seconds: rule.cooldown_seconds,
      is_active: rule.is_active,
    });
    setErr('');
    setOpen(true);
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setErr(''); setSaving(true);
    const payload = { ...form, camera: form.camera || null };
    try {
      if (editing) await api.patch(`/alerts/rules/${editing.id}/`, payload);
      else await api.post('/alerts/rules/', payload);
      setOpen(false);
      load();
    } catch (ex) {
      const d = ex.response?.data;
      setErr(typeof d === 'object' ? JSON.stringify(d) : 'Failed to save rule');
    } finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!confirm('Delete this rule?')) return;
    await api.delete(`/alerts/rules/${id}/`);
    load();
  };

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Alert rules</h1>
          <p className="text-sm text-slate-500">Trigger alerts when detections cross thresholds.</p>
        </div>
        <button className="btn-primary" onClick={openCreate}>+ New rule</button>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Trigger</th>
              <th className="px-4 py-3 font-medium">Camera</th>
              <th className="px-4 py-3 font-medium">Email</th>
              <th className="px-4 py-3 font-medium">Cooldown</th>
              <th className="px-4 py-3 font-medium">Active</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {loading ? (
              <tr><td colSpan="8" className="px-4 py-8 text-center text-slate-500">Loading…</td></tr>
            ) : rules.length === 0 ? (
              <tr><td colSpan="8" className="px-4 py-8 text-center text-slate-500">No rules yet.</td></tr>
            ) : rules.map((r) => {
              const cam = cameras.find((c) => c.id === r.camera);
              return (
                <tr key={r.id}>
                  <td className="px-4 py-3 font-medium">{r.name}</td>
                  <td className="px-4 py-3">{r.rule_type}</td>
                  <td className="px-4 py-3">{r.condition} {r.threshold_value}</td>
                  <td className="px-4 py-3">{cam ? cam.name : <span className="text-slate-400">All cameras</span>}</td>
                  <td className="px-4 py-3 text-xs">{r.notification_email || '—'}</td>
                  <td className="px-4 py-3">{r.cooldown_seconds}s</td>
                  <td className="px-4 py-3">
                    <span className={r.is_active ? 'badge-green' : 'badge-gray'}>{r.is_active ? 'on' : 'off'}</span>
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <button onClick={() => openEdit(r)} className="btn-secondary !py-1 !px-2 text-xs">Edit</button>
                    <button onClick={() => remove(r.id)} className="btn-danger !py-1 !px-2 text-xs">Delete</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? 'Edit rule' : 'New rule'}
        footer={
          <>
            <button className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button>
            <button form="rule-form" type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          </>
        }
      >
        <form id="rule-form" onSubmit={onSubmit} className="space-y-4">
          {err && <div className="rounded-md bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-sm p-2">{err}</div>}
          <div>
            <label className="label">Name</label>
            <input className="input" required value={form.name} onChange={(e) => setField('name', e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Organization</label>
              <select className="input" required value={form.organization} onChange={(e) => setField('organization', e.target.value)}>
                <option value="">Select…</option>
                {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Camera (optional)</label>
              <select className="input" value={form.camera} onChange={(e) => setField('camera', e.target.value)}>
                <option value="">All cameras</option>
                {cameras
                  .filter((c) => !form.organization || c.organization === form.organization)
                  .map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="label">Rule type</label>
              <select className="input" value={form.rule_type} onChange={(e) => setField('rule_type', e.target.value)}>
                <option value="people_count">People count</option>
                <option value="crowd_threshold">Crowd</option>
                <option value="intrusion">Intrusion</option>
                <option value="camera_offline">Camera offline</option>
              </select>
            </div>
            <div>
              <label className="label">Condition</label>
              <select className="input" value={form.condition} onChange={(e) => setField('condition', e.target.value)}>
                <option value="greater_than">Greater than</option>
                <option value="less_than">Less than</option>
                <option value="equals">Equals</option>
              </select>
            </div>
            <div>
              <label className="label">Threshold</label>
              <input className="input" type="number" step="any" required value={form.threshold_value}
                onChange={(e) => setField('threshold_value', Number(e.target.value))} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Notification email</label>
              <input className="input" type="email" value={form.notification_email}
                onChange={(e) => setField('notification_email', e.target.value)} />
            </div>
            <div>
              <label className="label">Cooldown (seconds)</label>
              <input className="input" type="number" min="0" value={form.cooldown_seconds}
                onChange={(e) => setField('cooldown_seconds', Number(e.target.value))} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.is_active} onChange={(e) => setField('is_active', e.target.checked)} />
            Rule active
          </label>
          {editing && (
            <p className="text-xs text-slate-500">Updated {fmtDate(editing.updated_at)}</p>
          )}
        </form>
      </Modal>
    </div>
  );
}
