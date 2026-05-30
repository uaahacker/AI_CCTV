import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api.js';
import Modal from '../components/Modal.jsx';
import { fmtDate, statusBadgeClass } from '../lib/format.js';

const empty = { organization: '', name: '', location: '', rtsp_url: '', is_active: true };

export default function Cameras() {
  const [cameras, setCameras] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [open, setOpen] = useState(false);
  // null = create mode; string id = edit mode (we PATCH that camera)
  const [editingId, setEditingId] = useState(null);
  // Held so we can show the masked URL as the placeholder in edit mode.
  const [maskedRtsp, setMaskedRtsp] = useState('');
  const [form, setForm] = useState(empty);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    const [c, o] = await Promise.all([api.get('/cameras/'), api.get('/organizations/')]);
    setCameras(c.data.results || c.data);
    setOrgs(o.data.results || o.data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const openCreate = () => {
    setEditingId(null);
    setMaskedRtsp('');
    setErr('');
    setForm({ ...empty, organization: orgs[0]?.id || '' });
    setOpen(true);
  };

  const openEdit = (cam) => {
    setEditingId(cam.id);
    setMaskedRtsp(cam.rtsp_url_masked || '');
    setErr('');
    setForm({
      organization: cam.organization,
      name: cam.name || '',
      location: cam.location || '',
      rtsp_url: '',                 // blank → keep existing URL on PATCH
      is_active: cam.is_active ?? true,
    });
    setOpen(true);
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setErr(''); setSaving(true);
    try {
      if (editingId) {
        // PATCH — only include rtsp_url when the user typed a replacement.
        const payload = {
          name: form.name,
          location: form.location,
          is_active: form.is_active,
        };
        if (form.rtsp_url && form.rtsp_url.trim()) payload.rtsp_url = form.rtsp_url.trim();
        await api.patch(`/cameras/${editingId}/`, payload);
      } else {
        await api.post('/cameras/', form);
      }
      setOpen(false);
      setForm(empty);
      setEditingId(null);
      load();
    } catch (ex) {
      const d = ex.response?.data;
      setErr(typeof d === 'object' ? JSON.stringify(d) : 'Failed to save camera');
    } finally { setSaving(false); }
  };

  const testConn = async (id) => {
    await api.post(`/cameras/${id}/test-connection/`);
    setTimeout(load, 1500);
  };

  const remove = async (id) => {
    if (!confirm('Delete this camera?')) return;
    await api.delete(`/cameras/${id}/`);
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Cameras</h1>
          <p className="text-sm text-slate-500">Manage RTSP/IP camera connections.</p>
        </div>
        <button className="btn-primary" onClick={openCreate}>+ Add camera</button>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Location</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Last seen</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {loading ? (
              <tr><td colSpan="5" className="px-4 py-8 text-center text-slate-500">Loading…</td></tr>
            ) : cameras.length === 0 ? (
              <tr><td colSpan="5" className="px-4 py-8 text-center text-slate-500">No cameras yet.</td></tr>
            ) : cameras.map((c) => (
              <tr key={c.id}>
                <td className="px-4 py-3">
                  <Link to={`/cameras/${c.id}`} className="font-medium hover:underline">{c.name}</Link>
                  <div className="text-xs text-slate-500 truncate max-w-xs">{c.rtsp_url_masked}</div>
                </td>
                <td className="px-4 py-3">{c.location || '—'}</td>
                <td className="px-4 py-3"><span className={statusBadgeClass(c.status)}>{c.status}</span></td>
                <td className="px-4 py-3 text-slate-500">{fmtDate(c.last_seen_at)}</td>
                <td className="px-4 py-3 text-right space-x-2">
                  <button onClick={() => openEdit(c)} className="btn-secondary !py-1 !px-2 text-xs">Edit</button>
                  <button onClick={() => testConn(c.id)} className="btn-secondary !py-1 !px-2 text-xs">Test</button>
                  <button onClick={() => remove(c.id)} className="btn-danger !py-1 !px-2 text-xs">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? 'Edit camera' : 'Add camera'}
        footer={
          <>
            <button className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button>
            <button form="cam-form" type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : (editingId ? 'Save changes' : 'Save')}
            </button>
          </>
        }
      >
        <form id="cam-form" onSubmit={onSubmit} className="space-y-4">
          {err && <div className="rounded-md bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-sm p-2">{err}</div>}
          <div>
            <label className="label">Organization</label>
            <select
              className="input"
              required
              disabled={!!editingId}
              value={form.organization}
              onChange={(e) => setForm({ ...form, organization: e.target.value })}
            >
              <option value="">Select…</option>
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
            {orgs.length === 0 && <p className="text-xs text-amber-600 mt-1">Create an organization first in Settings.</p>}
          </div>
          <div>
            <label className="label">Name</label>
            <input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <label className="label">Location</label>
            <input className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
          </div>
          <div>
            <label className="label">RTSP URL</label>
            <input
              className="input font-mono text-xs"
              placeholder={editingId ? (maskedRtsp || 'Leave blank to keep existing') : 'rtsp://user:pass@host:554/stream'}
              required={!editingId}
              value={form.rtsp_url}
              onChange={(e) => setForm({ ...form, rtsp_url: e.target.value })}
            />
            <p className="text-xs text-slate-500 mt-1">
              {editingId
                ? 'Leave blank to keep the current URL. Stored encrypted; credentials masked in responses.'
                : 'Stored encrypted. Credentials are masked in all responses.'}
            </p>
          </div>
          {editingId && (
            <div className="flex items-center gap-2">
              <input
                id="cam-active"
                type="checkbox"
                checked={!!form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              />
              <label htmlFor="cam-active" className="text-sm">Active (worker + streamer will process this camera)</label>
            </div>
          )}
        </form>
      </Modal>
    </div>
  );
}
