export default function StatCard({ label, value, hint, accent = 'brand' }) {
  const accents = {
    brand: 'from-brand-500/15 to-brand-500/0 text-brand-600',
    green: 'from-green-500/15 to-green-500/0 text-green-600',
    amber: 'from-amber-500/15 to-amber-500/0 text-amber-600',
    red: 'from-red-500/15 to-red-500/0 text-red-600',
  };
  return (
    <div className={`card p-5 bg-gradient-to-br ${accents[accent]}`}>
      <div className="text-sm text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-1 text-3xl font-semibold text-slate-900 dark:text-white">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}
