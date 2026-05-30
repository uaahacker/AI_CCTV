import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';

const PROVIDER_TYPES = [
  { value: 'disabled',          label: 'Disabled (no AI)' },
  { value: 'openrouter',        label: 'OpenRouter (cloud)' },
  { value: 'openai_compatible', label: 'OpenAI-compatible API' },
  { value: 'local_ollama',      label: 'Local Ollama' },
  { value: 'self_hosted',       label: 'Self-hosted (vLLM, LM Studio, …)' },
];

const DEFAULT_BASE_URL = {
  openrouter:        'https://openrouter.ai/api/v1',
  openai_compatible: 'https://api.openai.com/v1',
  local_ollama:      'http://ollama:11434/v1',
  self_hosted:       '',
  disabled:          '',
};

const PLACEHOLDER_MODEL = {
  openrouter:        'openrouter/auto',
  openai_compatible: 'gpt-4o-mini',
  local_ollama:      'llama3.1:8b',
  self_hosted:       'your-model-name',
  disabled:          '',
};

export default function AISettings() {
  const [orgs, setOrgs] = useState([]);
  const [orgId, setOrgId] = useState('');
  const [providers, setProviders] = useState([]);   // existing config(s) for this org
  const [form, setForm] = useState(blankForm());
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);             // { kind: 'ok'|'err', text }

  function blankForm() {
    return {
      provider_type: 'disabled',
      display_name: '',
      base_url: '',
      model_name: '',
      api_key: '',
      is_active: true,
    };
  }

  // Load organizations and pick first one.
  useEffect(() => {
    api.get('/organizations/').then((r) => {
      const list = r.data.results || r.data;
      setOrgs(list);
      if (list.length && !orgId) setOrgId(list[0].id);
    });
  }, []);

  // Load existing AI config when org changes.
  useEffect(() => {
    if (!orgId) return;
    api.get(`/ai/providers/?organization=${orgId}`).then((r) => {
      const list = r.data.results || r.data;
      setProviders(list);
      if (list.length) {
        const cur = list[0];
        setEditingId(cur.id);
        setForm({
          provider_type: cur.provider_type,
          display_name: cur.display_name || '',
          base_url: cur.base_url || '',
          model_name: cur.model_name || '',
          api_key: '',                  // never preload — backend never returns it
          is_active: cur.is_active,
        });
      } else {
        setEditingId(null);
        setForm(blankForm());
      }
    });
  }, [orgId]);

  const onProviderChange = (value) => {
    setForm((f) => ({
      ...f,
      provider_type: value,
      base_url: f.base_url || DEFAULT_BASE_URL[value] || '',
      model_name: f.model_name || PLACEHOLDER_MODEL[value] || '',
    }));
  };

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const payload = { ...form, organization: orgId };
      // Empty api_key means "leave existing key untouched" on PATCH.
      if (!payload.api_key) delete payload.api_key;

      const r = editingId
        ? await api.patch(`/ai/providers/${editingId}/`, payload)
        : await api.post('/ai/providers/', payload);
      setEditingId(r.data.id);
      setProviders([r.data]);
      setForm((f) => ({ ...f, api_key: '' }));
      setMsg({ kind: 'ok', text: 'Saved. API key is encrypted at rest and never returned to the browser.' });
    } catch (ex) {
      setMsg({ kind: 'err', text: ex.response?.data ? JSON.stringify(ex.response.data) : 'Save failed' });
    } finally {
      setBusy(false);
    }
  };

  const testConnection = async () => {
    if (!editingId) {
      setMsg({ kind: 'err', text: 'Save the configuration first, then test.' });
      return;
    }
    setBusy(true); setMsg(null);
    try {
      const r = await api.post(`/ai/providers/${editingId}/test-connection/`);
      setMsg({ kind: 'ok', text: `Connected: ${r.data.detail}` });
    } catch (ex) {
      const detail = ex.response?.data?.detail || 'Connection failed';
      setMsg({ kind: 'err', text: detail });
    } finally {
      setBusy(false);
    }
  };

  const current = providers[0];

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold">AI Settings</h1>
        <p className="text-sm text-slate-500">
          Configure the LLM provider used for alert summaries and report insights.
          Computer-vision detection (people counting) is always handled by the
          CV worker and does not use these settings.
        </p>
      </div>

      <div className="card p-5 space-y-3">
        <label className="block text-sm font-medium">Organization</label>
        <select className="input" value={orgId} onChange={(e) => setOrgId(e.target.value)}>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
        {current && (
          <div className="text-xs text-slate-500">
            Current key: <span className="font-mono">{current.masked_api_key || '(not set)'}</span>
          </div>
        )}
      </div>

      <form onSubmit={save} className="card p-5 space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Provider type</label>
          <select
            className="input"
            value={form.provider_type}
            onChange={(e) => onProviderChange(e.target.value)}
          >
            {PROVIDER_TYPES.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Display name</label>
          <input
            className="input"
            placeholder="e.g. Prod LLM"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Base URL</label>
          <input
            className="input font-mono text-sm"
            placeholder={DEFAULT_BASE_URL[form.provider_type] || 'https://...'}
            value={form.base_url}
            onChange={(e) => setForm({ ...form, base_url: e.target.value })}
          />
          <p className="text-xs text-slate-500 mt-1">
            For Ollama in Docker use <span className="font-mono">http://ollama:11434/v1</span>.
            Never expose Ollama publicly without auth.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Model name</label>
          <input
            className="input font-mono text-sm"
            placeholder={PLACEHOLDER_MODEL[form.provider_type] || 'model-id'}
            value={form.model_name}
            onChange={(e) => setForm({ ...form, model_name: e.target.value })}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">API key</label>
          <input
            type="password"
            autoComplete="new-password"
            className="input font-mono text-sm"
            placeholder={editingId && current?.has_api_key
              ? 'Leave blank to keep the existing key'
              : 'Paste your API key (encrypted at rest)'}
            value={form.api_key}
            onChange={(e) => setForm({ ...form, api_key: e.target.value })}
          />
          <p className="text-xs text-slate-500 mt-1">
            Stored encrypted with the server's FIELD_ENCRYPTION_KEY. Never logged,
            never returned to the browser. Ollama and most self-hosted endpoints
            don't need a key — leave blank.
          </p>
        </div>

        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
          />
          Active (uncheck to disable AI without losing the configuration)
        </label>

        <div className="flex gap-2 pt-2">
          <button className="btn-primary" disabled={busy}>
            {editingId ? 'Save changes' : 'Save'}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={testConnection}
            disabled={busy || !editingId}
          >
            Test connection
          </button>
        </div>

        {msg && (
          <div className={`text-sm ${msg.kind === 'ok' ? 'text-emerald-600' : 'text-red-600'}`}>
            {msg.text}
          </div>
        )}
      </form>
    </div>
  );
}
