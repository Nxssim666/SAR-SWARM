# fleet-console

Operator console of the SAR ground control system (React + TypeScript + Vite).
See the repository `README.md` and `docs/decisions/0005-frontend.md`.

```bash
npm ci                 # install exactly what package-lock.json pins
npm run dev            # http://127.0.0.1:5173, proxies /api to the fleet service on :8000
npm run lint && npm run typecheck && npm run test && npm run build
```

`FLEET_SERVICE_URL` overrides where the dev server proxies the API.
