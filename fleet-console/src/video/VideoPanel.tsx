// Live video (ADR 0012, M5): a panel over the map with a 1, 4 or 9 tile grid. Each tile asks
// the fleet service to view a stream (audited), plays it over WebRTC or LL-HLS, and shows
// its health (from the relay), transport and estimated latency; picture-in-picture and
// fullscreen per tile. At most 9 streams decode at once (the decode budget).
import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { api, ProblemError } from '../api/client';
import { useSession } from '../session/session';
import { type Codec, CodecUnsupported, type Playing, play } from './players';

interface Stream {
  id: string;
  name: string;
  aircraft_id: string | null;
  relay_path: string;
  codec: Codec;
  enabled: boolean;
}

interface Health {
  monitored: boolean;
  streams: { stream_id: string; state: string; bitrate_kbps: number | null }[];
}

interface Ticket {
  whep_url: string;
  hls_url: string;
  ticket: string; // sent to the relay with every request (M6, ADR 0036)
}

const LAYOUTS = [1, 4, 9] as const;
type Layout = (typeof LAYOUTS)[number];

const STATE_LABEL: Record<string, string> = {
  live: '● live',
  stalled: '❚❚ frozen',
  offline: '✕ no video',
  unknown: '? unknown',
};

export function VideoPanel({ onClose }: { onClose: () => void }) {
  const token = useSession((s) => s.session?.token ?? null);
  const streams = useQuery({
    queryKey: ['video-streams'],
    queryFn: ({ signal }) =>
      api<{ items: Stream[] }>('/video-streams?limit=200', { token, signal }),
  });
  const health = useQuery({
    queryKey: ['video-health'],
    refetchInterval: 2000,
    queryFn: ({ signal }) => api<Health>('/video-health', { token, signal }),
  });
  const [layout, setLayout] = useState<Layout>(4);
  const [shown, setShown] = useState<string[]>([]);
  const enabled = streams.data?.items.filter((s) => s.enabled) ?? [];

  const toggle = (id: string) => {
    setShown(
      (current) =>
        current.includes(id) ? current.filter((x) => x !== id) : [...current, id].slice(-layout), // the newest pushes out the oldest
    );
  };

  return (
    <section className="video-panel" aria-label="Video">
      <div className="row spread">
        <strong>Video</strong>
        <div className="row">
          {LAYOUTS.map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={layout === n}
              onClick={() => {
                setLayout(n);
                setShown((s) => s.slice(0, n));
              }}
            >
              {n === 1 ? '1' : n === 4 ? '2×2' : '3×3'}
            </button>
          ))}
          <button type="button" aria-label="Close video" onClick={onClose}>
            ✕
          </button>
        </div>
      </div>
      {!health.data?.monitored && (
        <p className="muted">The station has no video relay configured: health is unknown.</p>
      )}
      <div className="stream-picker" role="group" aria-label="Streams">
        {enabled.length === 0 && <span className="muted">No video streams registered.</span>}
        {enabled.map((s) => {
          const state = health.data?.streams.find((h) => h.stream_id === s.id)?.state ?? 'unknown';
          return (
            <label key={s.id} className="inline">
              <input
                type="checkbox"
                checked={shown.includes(s.id)}
                onChange={() => {
                  toggle(s.id);
                }}
              />{' '}
              {s.name} <span className={`stream-state state-${state}`}>{STATE_LABEL[state]}</span>
            </label>
          );
        })}
      </div>
      <div className={`video-grid grid-${String(layout)}`}>
        {shown.map((id) => {
          const stream = enabled.find((s) => s.id === id);
          const h = health.data?.streams.find((x) => x.stream_id === id);
          return stream ? (
            <VideoTile
              key={id}
              stream={stream}
              state={h?.state ?? 'unknown'}
              bitrate={h?.bitrate_kbps ?? null}
            />
          ) : null;
        })}
      </div>
    </section>
  );
}

function VideoTile({
  stream,
  state,
  bitrate,
}: {
  stream: Stream;
  state: string;
  bitrate: number | null;
}) {
  const token = useSession((s) => s.session?.token ?? null);
  const video = useRef<HTMLVideoElement>(null);
  const tile = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState<Playing | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current: Playing | null = null;
    const life = { cancelled: false }; // set by the cleanup, read after the awaits
    const element = video.current;
    if (!element) return;
    void (async () => {
      try {
        const ticket = await api<Ticket>(`/video-streams/${stream.id}/view`, {
          method: 'POST',
          token,
        });
        const started = await play(
          ticket.whep_url,
          ticket.hls_url,
          element,
          stream.codec,
          (m) => {
            setError(m);
          },
          ticket.ticket,
        );
        if (life.cancelled) {
          started.stop();
          return;
        }
        current = started;
        setPlaying(started);
      } catch (e) {
        setError(
          e instanceof ProblemError || e instanceof CodecUnsupported
            ? e.message
            : 'The stream could not be played.',
        );
      }
    })();
    return () => {
      life.cancelled = true;
      current?.stop();
    };
  }, [stream.id, stream.codec, token]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      void playing.latencyMs().then(setLatency);
    }, 2000);
    return () => {
      window.clearInterval(timer);
    };
  }, [playing]);

  return (
    <div
      ref={tile}
      className="video-tile"
      data-testid={`video-${stream.relay_path}`}
      data-transport={playing?.transport ?? ''}
      data-error={error ?? ''}
      data-latency-ms={latency === null ? '' : latency.toFixed(0)}
    >
      <video ref={video} autoPlay muted playsInline />
      <div className="video-overlay">
        <strong>{stream.name}</strong> · {STATE_LABEL[state] ?? state}
        {playing && ` · ${playing.transport === 'webrtc' ? 'WebRTC' : 'LL-HLS'}`}
        {latency !== null && ` · ~${latency.toFixed(0)} ms`}
        {bitrate !== null && ` · ${(bitrate / 1000).toFixed(1)} Mbit/s`}
        {error && <span className="error"> · {error}</span>}
      </div>
      <div className="video-actions">
        <button
          type="button"
          aria-label={`Picture in picture: ${stream.name}`}
          onClick={() => void video.current?.requestPictureInPicture().catch(() => undefined)}
        >
          ⧉
        </button>
        <button
          type="button"
          aria-label={`Fullscreen: ${stream.name}`}
          onClick={() => void tile.current?.requestFullscreen().catch(() => undefined)}
        >
          ⛶
        </button>
      </div>
    </div>
  );
}
