import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth.jsx';

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: '', password: '', full_name: '' });
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setErr(''); setLoading(true);
    try {
      await register(form.email, form.password, form.full_name);
      navigate('/dashboard');
    } catch (ex) {
      const data = ex.response?.data;
      setErr(typeof data === 'object' ? JSON.stringify(data) : 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-2xl font-semibold mb-1">Create your account</h1>
        <p className="text-sm text-slate-500 mb-6">Start monitoring your cameras in minutes.</p>
        {err && <div className="mb-4 rounded-md bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-sm p-3">{err}</div>}
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label">Full name</label>
            <input className="input" value={form.full_name} onChange={onChange('full_name')} />
          </div>
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" required value={form.email} onChange={onChange('email')} />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" required minLength={8} value={form.password} onChange={onChange('password')} />
          </div>
          <button className="btn-primary w-full" disabled={loading}>{loading ? 'Creating…' : 'Create account'}</button>
        </form>
        <p className="mt-6 text-sm text-slate-500 text-center">
          Already have an account? <Link className="text-brand-600 hover:underline" to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
