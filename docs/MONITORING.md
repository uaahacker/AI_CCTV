# Monitoring & observability

Three independent signals are wired in by default; all are zero-overhead
when their env vars are unset.

## 1. Health endpoint

`GET /api/health/` (public, no auth) returns JSON with three sub-checks:

```jsonc
{
  "status": "ok",
  "time":   "2025-06-01T12:34:56+00:00",
  "version": "dev",
  "checks": {
    "database": { "ok": true,  "detail": "ok" },
    "redis":    { "ok": true,  "detail": "ok" },
    "celery":   { "ok": true,  "detail": "ok", "workers": 2 }
  }
}
```

HTTP status:
- `200` — DB reachable (even if Celery / Redis are degraded).
- `503` — DB unreachable; load balancer should remove the pod.

Use it for ELB / k8s liveness + readiness probes.

## 2. Prometheus metrics

`GET /api/health/metrics/` returns the standard text exposition format.
Gated by `PROMETHEUS_METRICS_ENABLED=True` (default).

Exposed gauges:
- `aicctv_cameras_total` — fleet size.
- `aicctv_cameras_online` — cameras with status=online.
- `aicctv_alerts_open` — alerts in status=new.
- `aicctv_deliveries_failed_24h` — alert deliveries that failed in the past 24h.

Plus the default `prometheus_client` process collectors (memory, CPU, GC).

Scrape with the usual job in `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: aicctv
    metrics_path: /api/health/metrics/
    static_configs:
      - targets: ["cctv.example.com:443"]
    scheme: https
```

## 3. Sentry

Set `SENTRY_DSN` (and optionally `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`)
in the env file used by each container that should report errors:

| Service     | Init point |
|-------------|------------|
| backend (Django + Celery worker + Celery beat) | `backend/config/settings.py` |
| cv_worker   | `cv_worker/worker/main.py` |
| frontend    | `frontend/src/main.jsx` (`VITE_SENTRY_DSN`) |

PII is **never** sent by default (`send_default_pii=False`). Override
explicitly if your privacy policy allows it.

## Troubleshooting

- Sentry SDK not installed? The Django process logs a warning at startup
  and continues. Health endpoint is unaffected.
- Prometheus 404s? `PROMETHEUS_METRICS_ENABLED=False` was set.
- Celery check shows `workers: 0`? Beat scheduler runs but no workers
  consume tasks. Check `celery_worker` logs.
