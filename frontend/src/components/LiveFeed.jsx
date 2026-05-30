import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';

/**
 * Live HLS player for a single camera.
 *
 * Source: /media/hls/<cameraId>/index.m3u8 (written by the `streamer`
 * sidecar — see backend/apps/cameras/management/commands/run_hls_streamer.py).
 *
 * Props:
 *   - cameraId  (required)  UUID of the camera
 *   - className (optional)  extra Tailwind classes on the outer <div>
 *   - muted     (default true)  required for browser autoplay
 */
export default function LiveFeed({ cameraId, className = '', muted = true }) {
  const videoRef = useRef(null);
  const [status, setStatus] = useState('connecting'); // connecting | live | error
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!cameraId) return;
    const video = videoRef.current;
    if (!video) return;

    const src = `/media/hls/${cameraId}/index.m3u8`;
    let hls;
    let stallTimer;

    const armStallTimer = () => {
      clearTimeout(stallTimer);
      // If we never reach LEVEL_LOADED within 12s the playlist probably 404s.
      stallTimer = setTimeout(() => setStatus('error'), 12000);
    };

    if (Hls.isSupported()) {
      hls = new Hls({
        liveSyncDurationCount: 2,
        maxBufferLength: 6,
        lowLatencyMode: true,
      });
      hls.loadSource(src);
      hls.attachMedia(video);
      armStallTimer();
      hls.on(Hls.Events.LEVEL_LOADED, () => {
        clearTimeout(stallTimer);
        setStatus('live');
      });
      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (data.fatal) setStatus('error');
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari — native HLS
      video.src = src;
      armStallTimer();
      video.addEventListener('loadedmetadata', () => {
        clearTimeout(stallTimer);
        setStatus('live');
      });
      video.addEventListener('error', () => setStatus('error'));
    } else {
      setStatus('error');
    }

    return () => {
      clearTimeout(stallTimer);
      if (hls) hls.destroy();
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
          {status === 'connecting' && (
            <>
              <div className="animate-pulse">Connecting to live stream…</div>
              <div className="text-slate-400 mt-1">
                First frames take 5–15s while the transcoder warms up.
              </div>
            </>
          )}
          {status === 'error' && (
            <>
              <div className="text-amber-300 font-medium">Live stream unavailable</div>
              <div className="text-slate-400 mt-1">
                Check that the camera is active and the <code>streamer</code> container is running.
              </div>
              <button
                onClick={() => { setStatus('connecting'); setRetry((n) => n + 1); }}
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
