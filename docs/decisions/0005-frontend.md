# 0005. Frontend: React, TypeScript, Vite

- Status: Accepted
- Date: 2026-09-28

## Context

The console is a map-centric, real-time, high-cognitive-load application. It shows 25–50 moving
aircraft with trails, lists, panels, alerts and video, and it must never make a risky command
easy to trigger by accident. It needs good testability, accessibility and a long-lived ecosystem.

## Decision

- **React 19 + TypeScript** (strict, including `noUncheckedIndexedAccess` and
  `exactOptionalPropertyTypes`), bundled by **Vite**.
- **State split by update rate:**
  - *Live telemetry* (up to 10 Hz × 50 aircraft) goes into a **Zustand** store written by the
    WebSocket client. The map reads it outside React: MapLibre GeoJSON sources are updated
    at most once per animation frame. React components subscribe with selectors, and lists
    re-render at most about 4 Hz. Telemetry never goes through React context.
  - *Server resources* (missions, users, incidents) use **TanStack Query** over REST, with
    WebSocket events invalidating queries.
- **UI primitives:** a small set of accessible components, chosen in M3 (candidate: Radix UI
  primitives), styled with CSS variables. No heavy design-system dependency.
- **Tests:** Vitest + Testing Library for components and logic; Playwright for E2E, including
  anything that needs the WebGL map (ADR 0015).
- **Lint and format:** ESLint (typescript-eslint strict type-checked, react-hooks), Prettier.
- Versions at M0: React 19.3, TypeScript 6.0, Vite 8, Vitest 5, ESLint 10, Node 24 LTS.
- **API types are generated** from the committed OpenAPI document (ADR 0013). They are not
  hand-written after M1.

## Alternatives considered

- **Svelte/SvelteKit:** smaller and fast, with a fine developer experience, but a smaller
  ecosystem for maps, testing and accessible primitives, and fewer engineers know it.
- **Vue 3:** a viable choice. React wins on ecosystem breadth for map and real-time tooling.
- **Angular:** heavy, and its opinionated structure buys little for a single application.
- **Desktop app (Qt/QML, like QGroundControl):** strong offline story, but no multi-user
  access from tablets and slower UI iteration. The browser also makes multi-operator trivial,
  since every device on the LAN is a console.

## Consequences

- Operators need a WebGL-capable browser (ADR 0002, A11).
- The rate-split design must be enforced in review. A test in M3/M5 guards render counts
  under load.
