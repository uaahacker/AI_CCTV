# CV Pipeline

How frames travel from RTSP socket to a `DetectionEvent` row.

## 1. Per-camera worker

Every active `Camera` row spawns a daemon thread in `cv_worker/worker/main.py`
(`CameraWorker`). The supervisor periodically queries the DB to add/remove
threads as cameras are activated or deactivated.

```
main.py
  └─ supervisor loop
       ├─ start CameraWorker(camera_id, detector, stop_event)
       └─ wait CAMERA_REFRESH_SECONDS, repeat
```

## 2. Tick loop (per thread)

```python
while not stop_event.is_set():
    cam = Camera.objects.select_related("organization").get(id=self.camera_id)
    if not cam.is_active: return
    process_one(cam, self.detector)
    stop_event.wait(SAMPLE_INTERVAL_SECONDS)
```

`SAMPLE_INTERVAL_SECONDS` defaults to 5. Setting it lower increases CPU and
event volume linearly.

## 3. `process_one()` step by step

1. **Open** the stream:
   `RtspReader(camera.rtsp_url, open_timeout_s=RTSP_READ_TIMEOUT_SECONDS).read_one()`.
   Returns `ReadResult(ok, frame, latency_ms, error)`.
2. **Health record**: write a `CameraHealthCheck` row + update
   `Camera.status` + `Camera.last_seen_at`.
3. If the read failed → log + return early.
4. **Privacy preprocessing**: `frame = apply_privacy(result.frame)` —
   blurs every detected face (see [PRIVACY.md](PRIVACY.md)).
5. **Detection**: `det = detector.detect(frame)` returns
   `DetectionResult(people_count, confidence, metadata)`.
6. **Persist** a `DetectionEvent` row.
7. **Enqueue**: `evaluate_event.delay(event.id)`.
8. The local `frame` variable goes out of scope → garbage-collected.

## 4. `BaseDetector`

The detector contract is intentionally tiny so swapping models is trivial:

```python
class BaseDetector:
    name: str = "base"

    def warmup(self) -> None: ...
    def detect(self, frame: np.ndarray) -> DetectionResult: ...

@dataclass
class DetectionResult:
    people_count: int = 0
    confidence:   float = 0.0
    metadata:     dict[str, Any] = field(default_factory=dict)
```

Detectors must NOT block on I/O or persist anything. The pipeline owns
persistence.

## 5. Bundled detectors

### `DummyPeopleDetector` (`detectors/dummy.py`)
Sine-wave generator. Zero dependencies. Default for dev so the dashboard
shows realistic-looking activity without a real camera.

### `YOLOPeopleDetector` (`detectors/yolo.py`)
Lazy-loads `ultralytics.YOLO`. COCO class index 0 = "person". Weights are
downloaded automatically on first run; specify with `YOLO_MODEL=yolov8n.pt`
(default — fast, 6 MB) or `yolov8s.pt`, `yolov8m.pt` etc.

```bash
# To enable YOLO:
pip install ultralytics      # adds torch (~2 GB)
export DETECTOR=yolo
export YOLO_MODEL=yolov8n.pt
export YOLO_CONF=0.35
```

## 6. Choosing `DETECTOR`

| `DETECTOR=` | Use when |
|---|---|
| `dummy` | Local dev, demos, CI |
| `yolo`  | Production with a GPU or a CPU you can spare |

You can register additional detectors by:

1. Subclass `BaseDetector` in a new file under `cv_worker/worker/detectors/`.
2. Add it to `get_detector()` in `cv_worker/worker/detectors/__init__.py`.
3. Set the env var.

## 7. ONVIF / NVR / DVR

Most NVR/DVR appliances expose every channel as RTSP. The cv_worker treats
them identically — just put the channel URL in `Camera.rtsp_url`, e.g.
`rtsp://user:pass@nvr.lan:554/cam/realmonitor?channel=3&subtype=0`. Native
ONVIF auto-discovery (PTZ control, event subscription) is on the roadmap;
contributions welcome — see [CONTRIBUTING.md](../CONTRIBUTING.md).

## 8. Resource tuning

| Variable | Default | Effect |
|---|---|---|
| `SAMPLE_INTERVAL_SECONDS` | 5 | Lower → more events, more CPU |
| `RTSP_READ_TIMEOUT_SECONDS` | 10 | Lower → faster offline detection, more spurious offlines |
| `CAMERA_REFRESH_SECONDS` | 30 | How often the supervisor reloads the camera list |
| `RECONNECT_BACKOFF_SECONDS` | 5 | Wait time after a thread-level exception |

With YOLOv8n on CPU: budget ~150 ms/frame/camera. For 20 cameras at 5 s
interval that's well under 1 % average CPU. With YOLOv8m on GPU: comfortably
30+ cameras in real time.

## 9. What the detector never sees

- Audio
- EXIF metadata
- Original-resolution faces (they're blurred before `detect()`)
- Database rows (it receives only the numpy array)

This makes detectors easy to unit-test: feed them a synthetic numpy array,
assert on the returned `DetectionResult`.

## 10. Tracking & advanced events (roadmap)

The current `YOLOPeopleDetector` is stateless — every frame is independent,
so the same person crossing a frame for 5 ticks is counted 5 times in
`DetectionEvent` (one per tick). For directional counts (entry vs exit) you
need a tracker. Suggested next steps:

- Add a `BaseTracker` interface (`update(detections) -> list[Track]`).
- Implement `ByteTrack` or `SORT` (small dependency footprint).
- Persist tracks in memory keyed by `(camera_id, track_id)`.
- Add `LineCrossingDetector` and `LoiteringDetector` consumers that read
  the track stream and emit specialised `DetectionEvent`s
  (`event_type="line_crossing"` etc.).

The `AlertRule.RuleType` enum already includes the values these would emit
(`line_crossing`, `loitering`, `queue_length`, `dwell_time`), so no further
schema work is required.
