import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AuthProvider } from './lib/auth.jsx';
import './index.css';

// --- Sentry (optional) ----------------------------------------------------
// Initialised lazily so production bundle size doesn't grow when the
// VITE_SENTRY_DSN env var is unset.
const sentryDsn = import.meta.env?.VITE_SENTRY_DSN;
if (sentryDsn) {
  import('@sentry/react').then((Sentry) => {
    Sentry.init({
      dsn: sentryDsn,
      environment: import.meta.env?.VITE_SENTRY_ENVIRONMENT || 'production',
      tracesSampleRate: Number(import.meta.env?.VITE_SENTRY_TRACES_SAMPLE_RATE || 0.05),
      // We never send PII (form bodies / emails) by default \u2014 set to true
      // explicitly if your privacy policy allows it.
      sendDefaultPii: false,
    });
  }).catch(() => { /* ignore \u2014 monitoring must never break the app */ });
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
