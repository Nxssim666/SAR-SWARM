// Playing a relay stream (ADR 0012): WebRTC through WHEP first (sub-second latency), LL-HLS
// through hls.js when WebRTC does not connect in time. Each returns a stop function.
//
// A browser must be able to decode the stream's codec: Chrome and Edge decode H.264 (the
// aircraft baseline); builds without proprietary codecs (Playwright's Chromium, some Linux
// Chromium packages) do not. That is checked first and said plainly, never shown as a
// stream that plays but stays black.
import Hls from 'hls.js';

export type Transport = 'webrtc' | 'll-hls';

export interface Playing {
  transport: Transport;
  stop: () => void;
  /** Estimated glass-to-glass share this end can see: jitter buffer + half the RTT (ms). */
  latencyMs: () => Promise<number | null>;
}

const WEBRTC_TIMEOUT_MS = 5000;

export type Codec = 'h264' | 'h265' | 'unknown';

export class CodecUnsupported extends Error {
  constructor(codec: Codec) {
    super(
      `This browser cannot decode ${codec === 'h264' ? 'H.264' : 'H.265'} video: use Chrome or Edge.`,
    );
    this.name = 'CodecUnsupported';
  }
}

/** Whether this browser can decode `codec` over WebRTC or MSE (unknown: try). */
export function canDecode(codec: Codec, probe: CodecProbe = browserProbe): boolean {
  if (codec === 'unknown') return true;
  const [rtp, mse] =
    codec === 'h264'
      ? ['video/H264', 'video/mp4; codecs="avc1.42E01E"']
      : ['video/H265', 'video/mp4; codecs="hvc1.1.6.L93.B0"'];
  return probe.webrtc().includes(rtp) || probe.mse(mse);
}

export interface CodecProbe {
  webrtc: () => string[];
  mse: (type: string) => boolean;
}

const browserProbe: CodecProbe = {
  webrtc: () =>
    typeof RTCRtpReceiver === 'undefined'
      ? []
      : (RTCRtpReceiver.getCapabilities('video')?.codecs.map((c) => c.mimeType) ?? []),
  mse: (type) => typeof MediaSource !== 'undefined' && MediaSource.isTypeSupported(type),
};

/** Wait for ICE gathering to finish (non-trickle WHEP), at most `ms`. */
function gathered(pc: RTCPeerConnection, ms: number): Promise<void> {
  if (pc.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise((resolve) => {
    const timer = window.setTimeout(resolve, ms);
    pc.addEventListener('icegatheringstatechange', () => {
      if (pc.iceGatheringState === 'complete') {
        window.clearTimeout(timer);
        resolve();
      }
    });
  });
}

/** Headers of a relay request: the viewing ticket, when the station checks them (ADR 0036). */
function authorization(ticket: string | undefined): Record<string, string> {
  return ticket ? { Authorization: `Bearer ${ticket}` } : {};
}

export async function playWhep(
  url: string,
  video: HTMLVideoElement,
  ticket?: string,
): Promise<Playing> {
  const pc = new RTCPeerConnection({ iceServers: [] }); // LAN only, no STUN/TURN (ADR 0012)
  pc.addTransceiver('video', { direction: 'recvonly' });
  pc.addTransceiver('audio', { direction: 'recvonly' });
  const stream = new MediaStream();
  pc.ontrack = (event) => {
    stream.addTrack(event.track);
    video.srcObject = stream;
  };
  const stop = () => {
    pc.close();
    video.srcObject = null;
  };
  try {
    await pc.setLocalDescription(await pc.createOffer());
    await gathered(pc, 1500);
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp', ...authorization(ticket) },
      body: pc.localDescription?.sdp ?? '',
    });
    if (!response.ok) throw new Error(`WHEP answered HTTP ${String(response.status)}`);
    await pc.setRemoteDescription({ type: 'answer', sdp: await response.text() });
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        reject(new Error('WebRTC did not connect'));
      }, WEBRTC_TIMEOUT_MS);
      const check = () => {
        if (pc.connectionState === 'connected') {
          window.clearTimeout(timer);
          resolve();
        } else if (pc.connectionState === 'failed') {
          window.clearTimeout(timer);
          reject(new Error('WebRTC failed'));
        }
      };
      pc.addEventListener('connectionstatechange', check);
      check();
    });
  } catch (error) {
    stop();
    throw error;
  }
  return {
    transport: 'webrtc',
    stop,
    latencyMs: async () => {
      const found: { buffer: number | null; rtt: number | null } = { buffer: null, rtt: null };
      (await pc.getStats()).forEach((report: Record<string, unknown>) => {
        if (report.type === 'inbound-rtp' && report.kind === 'video') {
          const delay = Number(report.jitterBufferDelay);
          const emitted = Number(report.jitterBufferEmittedCount);
          if (emitted > 0) found.buffer = (delay / emitted) * 1000;
        }
        if (report.type === 'candidate-pair' && report.state === 'succeeded') {
          const r = Number(report.currentRoundTripTime);
          if (Number.isFinite(r)) found.rtt = r * 1000;
        }
      });
      return found.buffer === null ? null : found.buffer + (found.rtt ?? 0) / 2;
    },
  };
}

export function playHls(
  url: string,
  video: HTMLVideoElement,
  onError: (message: string) => void = () => undefined,
  ticket?: string,
): Playing {
  if (Hls.isSupported()) {
    const hls = new Hls({
      lowLatencyMode: true,
      liveSyncDurationCount: 1,
      xhrSetup: (xhr) => {
        for (const [name, value] of Object.entries(authorization(ticket))) {
          xhr.setRequestHeader(name, value);
        }
      },
    });
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (data.fatal) onError(`LL-HLS failed (${data.details})`);
    });
    hls.loadSource(url);
    hls.attachMedia(video);
    return {
      transport: 'll-hls',
      stop: () => {
        hls.destroy();
      },
      latencyMs: () => Promise.resolve(hls.latency > 0 ? hls.latency * 1000 : null),
    };
  }
  // Safari plays HLS natively, and cannot add headers: the ticket goes in the query.
  video.src = ticket ? `${url}?ticket=${encodeURIComponent(ticket)}` : url;
  return {
    transport: 'll-hls',
    stop: () => {
      video.removeAttribute('src');
      video.load();
    },
    latencyMs: () => Promise.resolve(null),
  };
}

/** WebRTC, or LL-HLS if it fails; the caller shows which. Throws CodecUnsupported first. */
export async function play(
  whepUrl: string,
  hlsUrl: string,
  video: HTMLVideoElement,
  codec: Codec,
  onError: (message: string) => void = () => undefined,
  ticket?: string,
): Promise<Playing> {
  if (!canDecode(codec)) throw new CodecUnsupported(codec);
  try {
    return await playWhep(whepUrl, video, ticket);
  } catch {
    return playHls(hlsUrl, video, onError, ticket);
  }
}
