import { NavLink } from 'react-router-dom';

const nav = [
  { to: '/dashboard', label: 'Dashboard', icon: '▦' },
  { to: '/cameras', label: 'Cameras', icon: '◉' },
  { to: '/alerts', label: 'Alerts', icon: '⚠' },
  { to: '/alerts/rules', label: 'Alert rules', icon: '⚑' },
  { to: '/reports', label: 'Reports', icon: '📊' },
  { to: '/billing', label: 'Billing', icon: '$' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
  { to: '/settings/ai', label: 'AI Settings', icon: '✨' },
];

export default function Sidebar() {
  return (
    <aside className="w-60 shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hidden md:flex flex-col">
      <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-brand-600 grid place-items-center text-white font-bold">AI</div>
          <div>
            <div className="font-semibold leading-tight">AI CCTV</div>
            <div className="text-xs text-slate-500">Analytics SaaS</div>
          </div>
        </div>
      </div>
      <nav className="p-3 flex-1 space-y-1">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/alerts' || item.to === '/settings'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition ${
                isActive
                  ? 'bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-100 font-medium'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`
            }
          >
            <span className="w-5 text-center">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-3 text-xs text-slate-400">v0.1.0 MVP</div>
    </aside>
  );
}
