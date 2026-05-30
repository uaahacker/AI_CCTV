import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api.js';

/**
 * `POST /api/auth/password/reset/request/` is rate-limited to 5/hour.
 * The server always returns 202 to prevent email enumeration, so we
 * surface the same confirmation message regardless of address validity.
 */
export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await api.post('/auth/password/reset/request/', { email });
      setSent(true);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not send reset link');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
      <form onSubmit={submit} className="card p-6 w-full max-w-md space-y-4">
        <h1 className="text-xl font-semibold">Forgot your password?</h1>
        {sent ? (
          <p className="text-sm text-slate-600 dark:text-slate-300">
            If an account exists for <span className="font-medium">{email}</span>, we just sent
            a reset link. It expires in 1 hour.
          </p>
        ) : (
          <>
            <p className="text-sm text-slate-500">
              Enter your email and we&apos;ll send you a one-time reset link.
            </p>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="input w-full"
            />
            {error && <div className="text-sm text-red-600">{error}</div>}
            <button type="submit" className="btn-primary w-full">Send reset link</button>
          </>
        )}
        <div className="text-sm text-center">
          <Link to="/login" className="text-brand-600 hover:underline">Back to sign in</Link>
        </div>
      </form>
    </div>
  );
}
