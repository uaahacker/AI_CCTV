"""Rolling-buffer evidence-clip writer.

We keep the last N seconds of decoded frames per camera in memory. When an
alertable event fires, we flush the buffer to an MP4 file under
``MEDIA_ROOT/clips/<camera_id>/<event_id>.mp4`` using OpenCV's VideoWriter
(``mp4v`` codec — present in every wheel build of opencv-python).

If OpenCV cannot encode (no codec, write permission denied, etc.), the writer
quietly returns ``None`` — the event still gets recorded, just without a
clip. We never raise into the pipeline.

The buffer length is capped to ``settings.EVIDENCE_CLIP_SECONDS`` (default 5)
to honour the privacy-by-default principle stated in the README.
"""
from __future__ import annotations

import logging
import os
from collections import deque
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class RollingClipBuffer:
    """Per-camera ring buffer of recent frames + the clip-flush operation."""

    def __init__(self, *, fps: float, seconds: int, output_root: str) -> None:
        self.fps = max(1.0, float(fps))
        self.seconds = max(1, int(seconds))
        self.output_root = Path(output_root)
        self._frames: deque = deque(maxlen=int(self.fps * self.seconds))

    def push(self, frame) -> None:
        # Copy is critical — OpenCV frames are views into mmap'd buffers and
        # may be overwritten in-place by the next read.
        try:
            self._frames.append(frame.copy())
        except AttributeError:
            # Frame is None or unsupported type — drop silently.
            return

    def flush(self, *, camera_id: str, event_id: str) -> Optional[str]:
        if not self._frames:
            return None
        try:
            import cv2  # local import — opencv is heavy
        except ImportError:
            logger.warning("OpenCV unavailable; cannot write evidence clip.")
            return None

        out_dir = self.output_root / "clips" / str(camera_id)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Cannot create clip dir %s: %s", out_dir, exc)
            return None
        out_path = out_dir / f"{event_id}.mp4"

        first = self._frames[0]
        try:
            h, w = first.shape[:2]
        except (AttributeError, ValueError):
            return None

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, self.fps, (w, h))
        if not writer.isOpened():
            logger.warning("VideoWriter failed to open %s", out_path)
            return None
        try:
            for frame in list(self._frames):
                writer.write(frame)
        finally:
            writer.release()

        if not out_path.exists() or out_path.stat().st_size == 0:
            try:
                if out_path.exists():
                    os.unlink(out_path)
            except OSError:
                pass
            return None

        # Return MEDIA_URL-relative path so the API can serve it.
        rel = out_path.relative_to(self.output_root).as_posix()
        return rel
