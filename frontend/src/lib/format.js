export function fmtDate(s) {
  if (!s) return '—';
  try { return new Date(s).toLocaleString(); } catch { return s; }
}

export function statusBadgeClass(status) {
  switch (status) {
    case 'online': return 'badge-green';
    case 'offline': return 'badge-red';
    case 'error': return 'badge-red';
    default: return 'badge-gray';
  }
}

export function severityBadgeClass(sev) {
  switch (sev) {
    case 'critical': return 'badge-red';
    case 'warning': return 'badge-amber';
    default: return 'badge-gray';
  }
}
