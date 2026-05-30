"""Management command: spawn ffmpeg per active camera → HLS segments.

Run as a long-lived sidecar service (see the ``streamer`` compose service).

For every ``Camera`` with ``is_active=True`` we keep one ffmpeg subprocess
running, ingesting the RTSP source and writing rolling HLS chunks to
``MEDIA_ROOT/hls/<camera_id>/index.m3u8``. The nginx in the frontend container
serves that path at ``/media/hls/...`` so the browser can play it via hls.js.

Design notes
------------
* We re-sync the desired camera set every ``--refresh`` seconds, so adding /
  pausing a camera in the dashboard takes effect within ~30s without a restart.
* We default to ``-c:v copy`` (no transcoding) for low CPU. If your camera
  emits a codec the browser can't decode (e.g. H.265) set the camera's
  ``stream_codec`` to ``h264`` (re-encode) — TODO: surface that in the UI.
* ffmpeg stderr is captured into ``MEDIA_ROOT/hls/<id>/ffmpeg.log`` so misconfigured
  RTSP URLs are debuggable without losing the rest of the fleet.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


HLS_SUBDIR = "hls"


class Command(BaseCommand):
    help = "Run a per-camera HLS transcoder loop (manages ffmpeg subprocesses)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh",
            type=int,
            default=int(os.environ.get("STREAMER_REFRESH_SECONDS", "5")),
            help="How often (seconds) to reconcile running ffmpegs vs the Camera table.",
        )
        parser.add_argument(
            "--reencode",
            action="store_true",
            default=os.environ.get("STREAMER_REENCODE", "0") == "1",
            help="Force H.264 re-encode (use when cameras emit H.265 / unsupported codec).",
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        if not shutil.which("ffmpeg"):
            self.stderr.write("ffmpeg binary not found on PATH — aborting.")
            sys.exit(1)

        media_root = Path(getattr(settings, "MEDIA_ROOT", "/app/media"))
        hls_root = media_root / HLS_SUBDIR
        hls_root.mkdir(parents=True, exist_ok=True)

        refresh = opts["refresh"]
        reencode = opts["reencode"]
        # cam_id -> (Popen, rtsp_url) so we can detect URL changes.
        processes: dict[str, tuple[subprocess.Popen, str]] = {}

        def shutdown(*_):
            self.stdout.write("[streamer] shutdown signal — stopping ffmpegs…")
            for cid in list(processes):
                self._stop(processes, cid)
            sys.exit(0)

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)

        self.stdout.write(
            f"[streamer] starting; refresh={refresh}s reencode={reencode} "
            f"root={hls_root}"
        )

        while True:
            try:
                self._sync_once(processes, hls_root, reencode)
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"[streamer] sync error: {exc!r}")
            time.sleep(refresh)

    # ------------------------------------------------------------------
    def _sync_once(
        self,
        processes: dict,
        hls_root: Path,
        reencode: bool,
    ) -> None:
        # Import here so Django apps are ready.
        from apps.cameras.models import Camera

        desired: dict[str, str] = {}
        for cam in Camera.objects.filter(is_active=True):
            try:
                url = cam.rtsp_url  # decrypts
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"[streamer] {cam.id}: cannot decrypt rtsp_url: {exc!r}")
                continue
            if url:
                desired[str(cam.id)] = url

        # 1. Start / restart missing OR when the RTSP URL changed
        for cid, url in desired.items():
            existing = processes.get(cid)
            proc = existing[0] if existing else None
            current_url = existing[1] if existing else None
            alive = proc is not None and proc.poll() is None

            if alive and current_url == url:
                continue  # nothing to do
            if alive and current_url != url:
                self.stdout.write(f"[streamer] {cid}: URL changed, restarting ffmpeg")
                self._stop(processes, cid)
            elif proc is not None:
                self.stdout.write(f"[streamer] {cid}: ffmpeg exited rc={proc.returncode}, restarting")

            new_proc = self._start(cid, url, hls_root, reencode)
            processes[cid] = (new_proc, url)

        # 2. Stop removed / deactivated
        for cid in list(processes):
            if cid not in desired:
                self.stdout.write(f"[streamer] {cid}: camera no longer active, stopping")
                self._stop(processes, cid)

    # ------------------------------------------------------------------
    def _start(
        self,
        cam_id: str,
        rtsp_url: str,
        hls_root: Path,
        reencode: bool,
    ) -> subprocess.Popen:
        out_dir = hls_root / cam_id
        out_dir.mkdir(parents=True, exist_ok=True)
        # Purge stale chunks from previous run so client never serves orphans.
        for p in out_dir.glob("*.ts"):
            try:
                p.unlink()
            except OSError:
                pass

        video_args = (
            ["-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency"]
            if reencode
            else ["-c:v", "copy"]
        )

        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "warning",
            "-rtsp_transport", "tcp",
            "-fflags", "+genpts",
            "-i", rtsp_url,
            "-an",
            *video_args,
            "-f", "hls",
            "-hls_time", "2",
            "-hls_list_size", "5",
            "-hls_flags", "delete_segments+omit_endlist+independent_segments",
            "-hls_segment_filename", str(out_dir / "seg-%05d.ts"),
            str(out_dir / "index.m3u8"),
        ]

        log_path = out_dir / "ffmpeg.log"
        self.stdout.write(f"[streamer] {cam_id}: spawn ffmpeg → {out_dir}")
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=open(log_path, "ab"),  # noqa: SIM115 — long-lived
        )

    # ------------------------------------------------------------------
    def _stop(self, processes: dict, cam_id: str) -> None:
        entry = processes.pop(cam_id, None)
        if entry is None:
            return
        proc = entry[0] if isinstance(entry, tuple) else entry
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
