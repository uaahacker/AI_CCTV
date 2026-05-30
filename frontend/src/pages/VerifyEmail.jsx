import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../lib/api.js';

/** Lands here from the email link `/verify-email/<token>`. */
export default function VerifyEmail() {
  const { token } = useParams();
  const [state, setState] = useState('working');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api.post('/auth/email/verify/confirm/', { token })
      .then(() => { if (!cancelled) setState('ok'); })
      .catch((err) => {
        if (cancelled) return;
        setState('error');
        setError(err?.response?.data?.detail || 'Invalid or expired link');
      });
    return () => { cancelled = true; };
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
      <div className="card p-6 w-full max-w-md space-y-4 text-center">
        {state === 'working' && <p>Verifying\u2026</p>}
        {state === 'ok' && (
          <>
            <h1 className="text-lg font-semibold">Email verified</h1>
            <Link to="/login" className="btn-primary inline-block">Continue to sign in</Link>
          </>
        )}
        {state === 'error' && (
          <>
            <h1 className="text-lg font-semibold text-red-600">Verification failed</h1>
            <p className="text-sm text-slate-500">{error}</p>
            <Link to="/login" className="text-brand-600 hover:underline">Go to sign in</Link>
          </>
        )}
      </div>
    </div>
  );
}
