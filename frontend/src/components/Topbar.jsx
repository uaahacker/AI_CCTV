import { useEffect, useState } from 'react';
import { useAuth } from '../lib/auth.jsx';

export default function Topbar() {
  const { user, logout } = useAuth();
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('theme', dark ? 'dark' : 'light');
  }, [dark]);

  return (
    <header className="h-14 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between px-6">
      <div className="text-sm text-slate-500">Welcome back, <span className="font-medium text-slate-800 dark:text-slate-100">{user?.full_name || user?.email}</span></div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setDark((d) => !d)}
          className="btn-secondary !py-1.5 !px-3"
          title="Toggle theme"
        >
          {dark ? '☀' : '☾'}
        </button>
        <button onClick={logout} className="btn-secondary !py-1.5 !px-3">Sign out</button>
      </div>
    </header>
  );
}
