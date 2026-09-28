# 0012. Video transport: MediaMTX and WebRTC

- Status: Accepted
- Date: 2026-09-28

## Context

Operators need live video from selected aircraft with low latency (under 1 s) for spotting
people. That means multi-stream layouts, picture-in-picture, fullscreen and visible stream
health. Sources vary: RTSP servers on companions, raw RTP from Gazebo or GStreamer, and SRT
over lossy links. Everything runs offline on the ground host, and browsers can't play RTSP.

## Decision

- **MediaMTX** (MIT, a single binary) relays video on the ground host.
  - **Ingest:** it pulls RTSP from aircraft, and accepts RTP/UDP and SRT pushes. SRT is
    preferred for lossy links because it retransmits.
  - **Output:** **WebRTC via WHEP** to browsers for sub-second latency, with **LL-HLS** as the
    fallback when WebRTC can't connect.
  - Optional recording to fMP4 segments on disk, with retention (ADR 0002, privacy).
- The fleet service owns **`VideoStream` metadata**: which aircraft, source, MediaMTX path,
  codec and state. It polls the MediaMTX API for health (publishing, readers, bitrate, packet
  loss) and raises alerts when a stream stalls.
- Browsers reach WHEP through the Caddy gateway on the same origin. WebRTC media uses UDP
  directly to the host on the LAN, with `webrtcAdditionalHosts` set to the host's LAN address.
  No STUN or TURN servers are needed offline.
- **Decode budget:** a grid shows at most 9 live streams at once, and the rest are
  on-demand. 25 simultaneous decodes would overload typical laptops. The limit is measured and
  tuned in M5.
- **Mock video** for simulation: one ffmpeg `testsrc2` stream per simulated aircraft, with the
  aircraft ID and a timestamp overlaid, published to MediaMTX. The timestamp shows latency.
- Viewing a stream and exporting a recording are audited.

## Alternatives considered

- **go2rtc:** MIT and similar, but more focused on home/NVR use. MediaMTX has broader ingest
  protocols and server-side metrics.
- **Janus:** GPL-3.0, with a plugin model that is more complex to operate.
- **SRS:** MIT and capable. MediaMTX was chosen for its operational simplicity (one binary,
  one YAML file).
- **Custom GStreamer `webrtcbin` / Pion service:** full control, but a lot of code to own.
- **MJPEG over HTTP:** trivial, but bandwidth-heavy, with no hardware decode.

## Consequences

- One more container, added in M5.
- H.265 WebRTC playback depends on the browser. H.264 is the baseline codec requirement for
  aircraft streams.
