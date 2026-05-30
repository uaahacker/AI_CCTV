# Privacy

Privacy is a first-class architectural concern, not a feature toggle. This
document describes the controls that are enforced by default and the controls
that are intentionally not built.

## 1. Defaults

| Control | Default | Where it lives |
|---|---|---|
| Face blur on every analysed frame | **ON** | `cv_worker/worker/privacy.py` |
| Facial recognition / identity matching | **OFF** | Not implemented; env switch `PRIVACY_FACIAL_RECOGNITION_ENABLED` |
| Raw-video storage | **NEVER** | Frames discarded after detection |
| RTSP-credential storage | Fernet-encrypted | `apps.cameras.models.Camera.rtsp_url` |
| AI-provider API-key storage | Fernet-encrypted | `apps.ai.models.AIProviderSetting.api_key` |
| API responses leak credentials | NO | `rtsp_url_masked`, `masked_api_key` only |

## 2. How face blur works

`apply_privacy(frame)` runs **before** any detector sees the frame:

1. Convert frame to grayscale.
2. Run OpenCV's Haar cascade (`haarcascade_frontalface_default.xml`,
   shipped with `opencv-python`) to locate face rectangles.
3. Replace each face rectangle with a strong Gaussian blur (kernel size
   proportional to face width). Blur is **irreversible** — no recoverable
   facial features remain.
4. Return the modified frame to the detector.

Important properties:

- The cascade is a **classifier**, not a recogniser. It locates faces; it
  does not identify them. No embeddings, no comparison against a database.
- No image is written to disk at any point.
- People-count accuracy is unaffected: YOLO detects whole-body silhouettes
  whose torsos and limbs remain visible.

## 3. Opting out (and why you usually shouldn't)

Set `PRIVACY_BLUR_FACES=False` in the environment. The CV worker logs a
warning at start-up. You should only do this if:

- You have a documented legal basis (e.g. internal-only camera in a
  staff-only area with explicit signage and consent records), AND
- Your jurisdiction permits it, AND
- You have updated your privacy notice + DPIA accordingly.

Setting `PRIVACY_FACIAL_RECOGNITION_ENABLED=True` only suppresses the
"warning-but-still-blur" code path. **No facial-recognition pipeline ships
with this project.** If you plug one in, do so behind an explicit consent
gate per data subject; do not call it "AI" — call it "biometric
identification" in your privacy notice, because that is what regulators
will call it.

## 4. Data minimisation

What is persisted per detection:

- `DetectionEvent.organization_id`, `camera_id`
- `event_type` (string enum)
- `people_count` (int)
- `confidence` (float)
- `metadata` (JSON — detector name + model name, nothing more by default)
- `created_at`

What is not persisted: bounding-box pixel coordinates, frames, frame
thumbnails, face crops, embeddings, gait, clothing colour, audio.

## 5. Retention

The project does not currently ship an automatic retention job. Recommended
production setup:

```sql
-- Postgres scheduled cleanup (run nightly)
DELETE FROM analytics_detectionevent
 WHERE created_at < NOW() - INTERVAL '90 days';

DELETE FROM cameras_camerahealthcheck
 WHERE created_at < NOW() - INTERVAL '14 days';

DELETE FROM alerts_alert
 WHERE created_at < NOW() - INTERVAL '365 days'
   AND status = 'resolved';
```

A Celery beat task wrapping these would be a clean PR contribution.

## 6. Subject Access Requests (GDPR)

The dataset is intentionally non-identifying, so most GDPR Article 15 requests
will resolve to "no personal data is held about you." Operators should still:

- Provide signage at every camera (legal requirement in most jurisdictions).
- Maintain a Record of Processing Activities (RoPA) — see
  [COMPLIANCE.md](COMPLIANCE.md).
- Be able to enumerate camera locations on request.

## 7. Evidence clips (`Alert.clip_path`)

If you choose to enable the 1-5 s evidence-clip writer (not in default
deployment), enforce:

- Clip duration capped at 5 s.
- Clip linked to exactly one `Alert.id`; never accessible by camera-id alone.
- Clip auto-deleted N days after the alert is `resolved`.
- Clip access logged in `apps.audit.AuditLog`.

## 8. Network privacy

- HTTPS enforced on every external webhook (Slack/Discord/generic) when
  `DEBUG=False`.
- LLM providers receive **only structured alert metadata**, never frames or
  image URLs. See [../AI_PROVIDERS.md](../AI_PROVIDERS.md) §"What the LLM
  sees".
- The optional bundled Ollama is bound to `127.0.0.1:11434` — never exposed
  to the public internet.

## 9. Code references

- `cv_worker/worker/privacy.py` — face-blur preprocessing.
- `cv_worker/worker/pipeline.py` — `apply_privacy` called before `Detector.detect`.
- `apps.common.security.encrypt_str` / `decrypt_str` — Fernet helpers.
- `apps.cameras.serializers.CameraSerializer` — exposes `rtsp_url_masked` only.
- `apps.ai.serializers.AIProviderSettingSerializer` — `api_key` is write-only.
