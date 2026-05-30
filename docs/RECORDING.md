# Recording library

Optional, opt-in **continuous MP4 recording** for any camera. Disabled by
default — the system stays footage-free until an operator explicitly
opts in.

## Why opt-in?

Storing raw footage shifts the legal posture of the deployment from
"analytics on a transient frame" to "video surveillance with persistent
records". You must update your data-processing consent and retention
policy before enabling this.

## Policies

`Camera.recording_policy` is one of:

| Value         | Behaviour |
|---------------|-----------|
| `off`         | No recording (default). Streamer still serves HLS for the live tab. |
| `continuous`  | HLS segments are promoted to hourly MP4s under `MEDIA_ROOT/recordings/<camera>/<YYYY>/<MM>/<DD>/<HH>.mp4`. |
| `motion`      | (Reserved.) Same as `continuous` today; future work: trigger by detection event. |

## How promotion works

1. The streamer container (`cmd: run_hls_streamer`) writes HLS
   `index.m3u8` + `.ts` chunks under `MEDIA_ROOT/hls/<camera>/`. Each
   chunk is ~2 seconds.
2. Celery beat fires `apps.cameras.recording_tasks.promote_recordings`
   every 15 minutes (configurable via `RECORDING_PROMOTE_INTERVAL_MINUTES`).
3. For each camera with `recording_policy=continuous`, the task picks up
   the `.ts` chunks from the **fully completed** previous hour(s) and
   concatenates them with `ffmpeg -c copy` (no re-encode → near-zero CPU)
   into a single MP4 with `+faststart` so it streams over HTTP.
4. A `Recording` row is created (`camera`, `started_at`, `ended_at`,
   `duration_s`, `size_bytes`, `file_path`).
5. The job is idempotent: it skips hours that already have a `Recording`
   row, so it self-heals after downtime (up to 6 hours look-back).

## Retention

`RECORDING_RETENTION_DAYS` (default 7) controls how long MP4s live on
disk. `apps.common.purge_expired_data` runs nightly at 03:00 and deletes
both the `Recording` row and the file. Set to `0` to disable promotion
entirely (kills the periodic task too).

## Serving downloads

`Recording.download_url` (returned by the API) is a short-lived HMAC URL
pointing at `/api/media/file/?path=&token=&expires=`. Tokens expire after
`MEDIA_URL_DEFAULT_TTL_SECONDS` (default 1h). The serving view re-checks
the path against `MEDIA_ROOT` to block path-traversal even if the token
verifier ever has a bug.

See [docs/CONFIGURATION.md](CONFIGURATION.md) for the full env-var list.

## UI

- `/recordings` lists every recording in the user's organisations with
  inline `<video>` playback + download buttons.
- `/cameras/<id>` adds a **Recordings** tab and a **Recording policy**
  dropdown in the right rail.
