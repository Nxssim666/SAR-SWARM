# 0015. Testing strategy

- Status: Accepted
- Date: 2026-09-28

## Context

This is safety-relevant software. It's built incrementally, and much of it can't be exercised
on the development host: there is no PX4 SITL, ROS 2 or Docker on Windows. Testing is not
deferred to a later milestone, so each milestone ships its own tests at every relevant layer.

## Decision

| Layer | Tools | What | Where it runs |
|---|---|---|---|
| Unit | pytest, **Hypothesis** | Domain logic: command rules, state machines, geo validation. Search patterns get property tests: full coverage for the given sweep width, every waypoint inside area + margin, lane spacing within tolerance. Deconfliction invariants. | Every push |
| API | pytest + httpx (in-process ASGI) | Every endpoint, including an **authorization matrix** that checks every endpoint × every role for the expected status. Also the WebSocket protocol. | Every push |
| Contract | **Schemathesis**, JSON Schema validation, spec drift check | OpenAPI conformance, WebSocket message schemas, and committed specs matching the code (ADR 0013). The console's generated types compile. | Every push |
| Component | Vitest + Testing Library | Console components, stores, confirmation flows | Every push |
| Integration | pytest + Docker | Fleet service with PX4 SITL (SIH) for 1 and 5 aircraft: telemetry, mission upload, commands, failure injection. The ROS 2 bridge against a ROS container. | CI Linux job; nightly for Gazebo |
| End-to-end | **Playwright** | Console + fleet service + mock fleet in compose: operator scenarios, keyboard-only paths, the map | Every push (mock); nightly (SITL) |
| Load and performance | asyncio harness with the mock driver; SIH for 25/50 | Telemetry-to-console latency p50/p95/p99, CPU, memory, WebSocket bandwidth, console frame rate. **Budgets fail the test.** | Nightly; M5 gates |
| Safety regression | pytest | **One test per rule in ADR 0011 and per principle S1–S7 in ADR 0002** | Every push |
| Onboard | existing `src/swarm_sar/test` | Unchanged, stays green | Every push |

### Principles

- Tests go in the same change as the code. A bug fix starts with a failing test. For
  safety-relevant fixes, follow the onboard practice: revert the fix and confirm the test fails.
- Tests use **explicit settings and seeds** and never depend on the developer's environment,
  network or wall-clock timing. Time is injected.
- Warnings are errors in the fleet-service test run (`filterwarnings = error`).
- Everything that can't run on the development host is run in CI and **reported as not run
  locally**, never as passing.

### Usability acceptance (M3–M6)

These are scripted scenarios with measurable criteria:

- Selecting 10 aircraft by lasso and sending HOLD takes at most N actions.
- Every risky command shows a confirmation that names the aircraft count.
- No risky command can be triggered by a single keystroke.
- Alerts are distinguishable by more than color alone.

## Consequences

- CI needs a Linux runner with Docker for integration and E2E tests. A 50-aircraft SIH run
  likely needs a larger or self-hosted runner (risk tracked in PLAN.md).
- The mock driver must be good enough to make E2E meaningful (ADR 0010), and its limits are
  documented.
