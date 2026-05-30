import { useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { api } from '../lib/api.js';

/** Lands here from the email link `/reset-password/<token>`. */
export default function ResetPassword() {
  const { token } = useParams();
  const nav = useNavigate();
  const [pwd, setPwd] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (pwd !== confirm) { setError('Passwords do not match'); return; }
    if (pwd.length < 8)  { setError('Use at least 8 characters');  return; }
    setBusy(true);
    try {
      await api.post('/auth/password/reset/confirm/', { token, new_password: pwd });
      nav('/login?reset=1', { replace: true });
    } catch (err) {
      const d = err?.response?.data?.detail;
      setError(Array.isArray(d) ? d.join(' ') : (d || 'Invalid or expired link'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
      <form onSubmit={submit} className="card p-6 w-full max-w-md space-y-4">
        <h1 className="text-xl font-semibold">Set a new password</h1>
        <input
          type="password" required minLength={8}
          value={pwd} onChange={(e) => setPwd(e.target.value)}
          placeholder="New password" className="input w-full"
        />
        <input
          type="password" required minLength={8}
          value={confirm} onChange={(e) => setConfirm(e.target.value)}
          placeholder="Confirm password" className="input w-full"
        />
        {error && <div className="text-sm text-red-600">{error}</div>}
        <button disabled={busy} className="btn-primary w-full">
          {busy ? 'Updating\u2026' : 'Update password'}
        </button>
        <div className="text-sm text-center">
          <Link to="/login" className="text-brand-600 hover:underline">Back to sign in</Link>
        </div>
      </form>
    </div>
  );
}
