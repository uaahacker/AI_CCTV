"""Promote HLS .ts segments into hourly MP4 recordings.

Why a separate task instead of teaching the streamer to dual-write?
- The streamer is a thin ffmpeg supervisor; keeping it stateless makes
  recovery (process death) trivial.
- The promotion job runs every 15 min via Celery beat. It uses ``ffmpeg
  -c copy`` so there's zero re-encode cost \u2014 it just stitches the
  segments and slaps an MP4 container on them.

Files land under::

    MEDIA_ROOT/recordings/<camera_id>/<YYYY>/<MM>/<DD>/<HH>.mp4

Old MP4s are deleted by ``apps.common.tasks.purge_expired_data`` based on
``settings.RECORDING_RETENTION_DAYS``.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone as _tz

from celery import shared_task
from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)


def _segments_for_hour(hls_dir: str, hour_start: datetime, hour_end: datetime) -> list[str]:
    """Return absolute paths to .ts segments whose mtime falls in [start, end)."""
    if not os.path.isdir(hls_dir):
        return []
    out: list[str] = []
    for name in sorted(os.listdir(hls_dir)):
        if not name.endswith(".ts"):
            continue
        full = os.path.join(hls_dir, name)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(full), tz=_tz.utc)
        except OSError:
            continue
        if hour_start <= mtime < hour_end:
            out.append(full)
    return out


def _concat_to_mp4(segments: list[str], output: str) -> tuple[bool, int]:
    """Use ffmpeg's concat demuxer to stitch .ts files into a single MP4.

    Returns ``(ok, size_bytes)``. No re-encode \u2014 just a container swap.
    """
    if not segments:
        return False, 0
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        list_path = f.name
        for seg in segments:
            # ffmpeg's concat demuxer requires single-quoted, escaped paths.
            safe = seg.replace("'", "'\\''")
            f.write(f"file '{safe}'\n")
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-c", "copy", "-movflags", "+faststart",
            output,
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if proc.returncode != 0:
            log.warning("ffmpeg concat failed for %s: %s", output, proc.stderr[:500])
            return False, 0
        return True, os.path.getsize(output) if os.path.isfile(output) else 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        log.warning("ffmpeg concat error: %s", exc)
        return False, 0
    finally:
        try:
            os.unlink(list_path)
        except OSError:
            pass


@shared_task(name="apps.cameras.recording_tasks.promote_recordings")
def promote_recordings() -> dict:
    """For each camera with ``recording_policy=continuous`` promote any
    completed hour of HLS segments into a single MP4. Idempotent: skips
    hours that already have a Recording row.
    """
    from .models import Camera, Recording

    if int(getattr(settings, "RECORDING_RETENTION_DAYS", 7) or 0) <= 0:
        return {"skipped": "retention=0"}

    media_root = str(settings.MEDIA_ROOT)
    now = timezone.now()
    # We only promote hours that fully completed (so the "current hour"
    # is excluded). Look back up to 6 hours so we self-heal after worker
    # downtime; existing rows are skipped via the unique constraint below.
    hour_starts = []
    cursor = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    for _ in range(6):
        hour_starts.append(cursor)
        cursor -= timedelta(hours=1)

    summary = {"promoted": 0, "skipped": 0, "cameras": 0}
    for cam in Camera.objects.filter(
        recording_policy=Camera.RecordingPolicy.CONTINUOUS, is_active=True
    ):
        summary["cameras"] += 1
        hls_dir = os.path.join(media_root, "hls", str(cam.id))
        for h_start in hour_starts:
            h_end = h_start + timedelta(hours=1)
            rel_dir = os.path.join(
                "recordings", str(cam.id),
                f"{h_start:%Y}", f"{h_start:%m}", f"{h_start:%d}",
            )
            rel_path = os.path.join(rel_dir, f"{h_start:%H}.mp4").replace("\\", "/")
            if Recording.objects.filter(camera=cam, file_path=rel_path).exists():
                summary["skipped"] += 1
                continue
            segments = _segments_for_hour(hls_dir, h_start, h_end)
            if not segments:
                continue
            abs_out = os.path.join(media_root, rel_path)
            ok, size = _concat_to_mp4(segments, abs_out)
            if ok:
                Recording.objects.create(
                    camera=cam,
                    kind=Recording.Kind.CONTINUOUS,
                    started_at=h_start,
                    ended_at=h_end,
                    duration_s=3600,
                    size_bytes=size,
                    file_path=rel_path,
                )
                summary["promoted"] += 1
    log.info("promote_recordings: %s", summary)
    return summary
