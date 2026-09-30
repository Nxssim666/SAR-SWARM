import { describe, expect, it } from 'vitest';

import { canDecode, type CodecProbe } from './players';

function probe(webrtc: string[], mse: string[] = []): CodecProbe {
  return { webrtc: () => webrtc, mse: (type) => mse.some((m) => type.includes(m)) };
}

describe('codec support', () => {
  it('plays H.264 where WebRTC or MSE decodes it', () => {
    expect(canDecode('h264', probe(['video/VP8', 'video/H264']))).toBe(true);
    expect(canDecode('h264', probe(['video/VP8'], ['avc1']))).toBe(true);
  });

  it('refuses H.264 in a browser without it (Playwright Chromium: VP8, VP9, AV1 only)', () => {
    const chromium = probe(['video/VP8', 'video/VP9', 'video/AV1'], ['vp09']);
    expect(canDecode('h264', chromium)).toBe(false);
    expect(canDecode('h265', chromium)).toBe(false);
    expect(canDecode('unknown', chromium)).toBe(true); // unknown codec: try, and report
  });
});
