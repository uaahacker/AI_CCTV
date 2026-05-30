import { useEffect, useState } from 'react';
import { useAuth } from '../lib/auth.jsx';

export default function Topbar({ onMenuClick }) {
  const { user, logout } = useAuth();
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('theme', dark ? 'dark' : 'light');
  }, [dark]);

  const displayName = user?.full_name || user?.email || '';

  return (
    <header className="h-14 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between gap-3 px-3 sm:px-6">
      <div className="flex items-center gap-2 min-w-0">
        <button
          type="button"
          onClick={onMenuClick}
          className="md:hidden btn-secondary !py-1.5 !px-2.5"
          aria-label="Open menu"
        >
          {/* Hamburger — inline SVG so we don't pull a new icon dep */}
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="3" y1="6"  x2="21" y2="6"  />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <div className="text-sm text-slate-500 truncate">
          <span className="hidden sm:inline">Welcome back, </span>
          <span className="font-medium text-slate-800 dark:text-slate-100">{displayName}</span>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
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
