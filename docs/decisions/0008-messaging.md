# 0008. Messaging: event bus interface, NATS for out-of-process adapters

- Status: Accepted; which bus carries what is refined by [0024](0024-swarm-bridge-and-nats.md) (NATS only at the adapter boundary)
- Date: 2026-09-28

## Context

Several flows move through the system:

- Telemetry from drivers.
- Commands to drivers.
- Alerts, mission and command events.
- Audit events.
- WebSocket fan-out to consoles.

In M1 everything runs in one process. From M2, the ROS 2 bridge must run out of process in a
ROS container (ADR 0003), and simulator tooling and video health checks may too. The flows need
different delivery guarantees.

## Decision

- Code depends on a small **`EventBus` interface**: `publish(subject, message)`,
  `subscribe(pattern)` returning an async iterator, and `request(subject, message, timeout)`.
- **Delivery classes** are explicit per subject family:
  - **Telemetry: latest-value-wins.** Bounded per-subscriber queues coalesce per aircraft,
    so a slow consumer sees fewer updates but never stale backlogs. Telemetry is never
    queued unboundedly.
  - **Commands:** request/reply with a timeout. The outcome (ack, nack or timeout) is always
    reported and audited, and a command is never dropped silently.
  - **Alerts and events:** reliable. Consumers resync from the database after a gap, detected
    by sequence numbers.
- **M1: in-process implementation** built on asyncio.
- **M2: NATS** (Apache-2.0, a single small binary) once adapters run out of process.
  JetStream is used only where replay is needed, for events and command outcomes.
- Subject naming:
  - `sar.v1.aircraft.<aircraft_id>.telemetry`
  - `sar.v1.aircraft.<aircraft_id>.command`
  - `sar.v1.alerts`
  - `sar.v1.missions.<mission_id>`
  - `sar.v1.audit`

## Alternatives considered

- **MQTT (Mosquitto):** field-proven on constrained links, with a good QoS model. Its
  request/reply is weaker and there's no built-in replay stream. A reasonable second choice.
- **Redis Streams:** Redis licensing has changed repeatedly (Valkey is the BSD fork), and it
  would mean running another data store.
- **ZeroMQ:** no broker to run, but reliability and replay would all have to be built in-house.
- **Kafka/Redpanda:** built for throughput and retention far beyond 500 msg/s, with heavy
  operations for a field laptop.
- **ROS 2 / DDS as the bus:** couples every component to ROS. DDS discovery over Wi-Fi
  multicast is also fragile, so DDS stays inside the bridge.

## Consequences

- M1 needs no broker, which keeps development and tests simple.
- The interface must not leak NATS specifics. Tests run against both implementations from M2.
- NATS adds one container in M2, and it runs natively on Windows for development.
