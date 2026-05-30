import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { fmtDate } from '../lib/format.js';

/**
 * GDPR data-processing consent. Lists historical consent records and lets
 * an owner / admin record a fresh consent on behalf of the organisation.
 */
export default function Compliance() {
  const [orgs, setOrgs] = useState([]);
  const [consents, setConsents] = useState([]);
  const [form, setForm] = useState({
    organization: '',
    written_consent: false,
    camera_ownership: false,
    data_processing_terms: false,
    notes: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    const [o, c] = await Promise.all([
      api.get('/organizations/'),
      api.get('/compliance/consents/'),
    ]);
    setOrgs(o.data.results || o.data);
    setConsents(c.data.results || c.data);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.organization) { setError('Pick an organisation'); return; }
    if (!(form.written_consent && form.camera_ownership && form.data_processing_terms)) {
      setError('All three affirmations are required.');
      return;
    }
    setBusy(true);
    try {
      await api.post('/compliance/consents/', form);
      setForm({
        organization: form.organization,
        written_consent: false, camera_ownership: false, data_processing_terms: false,
        notes: '',
      });
      load();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not record consent');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Data processing &amp; consent</h1>

      <form onSubmit={submit} className="card p-5 space-y-4">
        <h2 className="font-semibold">Record a new consent</h2>
        <p className="text-sm text-slate-500">
          By submitting you affirm, on behalf of the selected organisation, that you have all
          required permissions to deploy analytics on the listed cameras and accept our terms.
        </p>

        <select
          className="input w-full"
          value={form.organization}
          onChange={(e) => setForm({ ...form, organization: e.target.value })}
        >
          <option value="">Pick organisation\u2026</option>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>

        {[
          ['written_consent', 'Written consent has been obtained from subjects where required by law.'],
          ['camera_ownership', 'We own or have a contractual right to operate the cameras in scope.'],
          ['data_processing_terms', 'We accept the data-processing terms (analytics only; no raw footage retention).'],
        ].map(([k, label]) => (
          <label key={k} className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={form[k]}
              onChange={(e) => setForm({ ...form, [k]: e.target.checked })}
              className="mt-1"
            />
            <span>{label}</span>
          </label>
        ))}

        <textarea
          className="input w-full" rows={3} placeholder="Notes (optional)"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
        />

        {error && <div className="text-sm text-red-600">{error}</div>}
        <button disabled={busy} className="btn-primary">
          {busy ? 'Saving\u2026' : 'Record consent'}
        </button>
      </form>

      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold">
          Consent history
        </div>
        <div className="table-scroll">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900 text-left">
              <tr>
                <th className="px-4 py-2">When</th>
                <th className="px-4 py-2">Version</th>
                <th className="px-4 py-2">Affirmations</th>
                <th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {consents.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                  No consent records yet.
                </td></tr>
              )}
              {consents.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-2 whitespace-nowrap">{fmtDate(c.created_at)}</td>
                  <td className="px-4 py-2">v{c.terms_version}</td>
                  <td className="px-4 py-2 text-xs">
                    {c.written_consent ? 'W' : '-'}{' '}
                    {c.camera_ownership ? 'O' : '-'}{' '}
                    {c.data_processing_terms ? 'T' : '-'}
                  </td>
                  <td className="px-4 py-2">
                    {c.revoked_at
                      ? <span className="badge-red">revoked</span>
                      : <span className="badge-green">valid</span>}
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
