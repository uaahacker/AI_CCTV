export default function Modal({ open, onClose, title, children, footer }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/50 p-3 sm:p-4 overflow-y-auto" onClick={onClose}>
      <div
        className="card w-full max-w-lg p-4 sm:p-5 my-4 max-h-[calc(100vh-2rem)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4 shrink-0">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-800 dark:hover:text-white text-2xl leading-none" aria-label="Close">×</button>
        </div>
        <div className="overflow-y-auto -mx-1 px-1">{children}</div>
        {footer && <div className="mt-5 flex flex-wrap justify-end gap-2 shrink-0">{footer}</div>}
      </div>
    </div>
  );
}
