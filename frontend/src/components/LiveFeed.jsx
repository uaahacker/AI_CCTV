import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';

/**
 * Live HLS player for a single camera.
 *
 * Source: /media/hls/<cameraId>/index.m3u8 (written by the `streamer`
 * sidecar — see backend/apps/cameras/management/commands/run_hls_streamer.py).
 *
 * Lifecycle:
 *   1. 'waiting'    — HEAD-poll the m3u8 every 2s until it appears
 *                     (newly-added cameras need ~5–15s for the streamer to
 *                     spawn ffmpeg and write the first 2 segments).
 *   2. 'connecting' — playlist exists, hls.js is loading the first level.
 *   3. 'live'       — first level loaded, playback started.
 *   4. 'error'      — gave up; show Retry button.
 */
const WAIT_TIMEOUT_MS = 60000;   // total time to wait for m3u8 to first appear
const WAIT_INTERVAL_MS = 2000;   // HEAD-poll cadence while waiting
const HLS_STALL_MS = 15000;      // after playlist exists, max time to first frame

export default function LiveFeed({ cameraId, className = '', muted = true }) {
  const videoRef = useRef(null);
  const [status, setStatus] = useState('waiting');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!cameraId) return undefined;
    const video = videoRef.current;
    if (!video) return undefined;

    const src = `/media/hls/${cameraId}/index.m3u8`;
    let hls;
    let pollTimer;
    let stallTimer;
    let cancelled = false;
    const startedAt = Date.now();

    setStatus('waiting');

    const attachHls = () => {
      if (cancelled) return;
      setStatus('connecting');
      clearTimeout(stallTimer);
      stallTimer = setTimeout(() => {
        if (!cancelled) setStatus('error');
      }, HLS_STALL_MS);

      if (Hls.isSupported()) {
        hls = new Hls({
          liveSyncDurationCount: 2,
          maxBufferLength: 6,
          lowLatencyMode: true,
        });
        hls.loadSource(src);
        hls.attachMedia(video);
        hls.on(Hls.Events.LEVEL_LOADED, () => {
          clearTimeout(stallTimer);
          if (!cancelled) setStatus('live');
        });
        hls.on(Hls.Events.ERROR, (_e, data) => {
          // Non-fatal hiccups (segment 404 during rotation) are common —
          // let hls.js auto-recover. Only escalate truly fatal errors.
          if (data.fatal) {
            try { hls.destroy(); } catch (_) { /* ignore */ }
            if (!cancelled) setStatus('error');
          }
        });
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = src;
        video.addEventListener('loadedmetadata', () => {
          clearTimeout(stallTimer);
          if (!cancelled) setStatus('live');
        }, { once: true });
        video.addEventListener('error', () => {
          if (!cancelled) setStatus('error');
        }, { once: true });
      } else {
        setStatus('error');
      }
    };

    // Poll for the m3u8 file before letting hls.js touch it. This avoids the
    // "first add → 404 → permanent error" UX: we patiently wait while the
    // streamer container spawns ffmpeg and writes the first 2 segments.
    const poll = async () => {
      if (cancelled) return;
      try {
        const res = await fetch(src, { method: 'HEAD', cache: 'no-store' });
        if (res.ok) {
          attachHls();
          return;
        }
      } catch (_) {
        // network blip — fall through and retry
      }
      if (Date.now() - startedAt > WAIT_TIMEOUT_MS) {
        if (!cancelled) setStatus('error');
        return;
      }
      pollTimer = setTimeout(poll, WAIT_INTERVAL_MS);
    };
    poll();

    return () => {
      cancelled = true;
      clearTimeout(pollTimer);
      clearTimeout(stallTimer);
      if (hls) {
        try { hls.destroy(); } catch (_) { /* ignore */ }
      }
      try { video.removeAttribute('src'); video.load(); } catch (_) { /* ignore */ }
    };
  }, [cameraId, retry]);

  return (
    <div className={`relative bg-black rounded-lg overflow-hidden ${className}`}>
      <video
        ref={videoRef}
        className="w-full h-full object-contain"
        autoPlay
        playsInline
        muted={muted}
        controls
      />
      {status !== 'live' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center text-xs text-slate-200 bg-black/70 p-3">
          {status === 'waiting' && (
            <>
              <div className="animate-pulse">Waiting for stream…</div>
              <div className="text-slate-400 mt-1">
                The transcoder starts ffmpeg within ~5s of the camera being added,
                then needs ~10s to buffer the first segments.
              </div>
            </>
          )}
          {status === 'connecting' && (
            <div className="animate-pulse">Connecting to live stream…</div>
          )}
          {status === 'error' && (
            <>
              <div className="text-amber-300 font-medium">Live stream unavailable</div>
              <div className="text-slate-400 mt-1">
                Check that the camera is active and the RTSP URL is reachable.
              </div>
              <button
                onClick={() => { setStatus('waiting'); setRetry((n) => n + 1); }}
                className="mt-2 px-3 py-1 rounded bg-brand-600 hover:bg-brand-500 text-white"
              >
                Retry
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
