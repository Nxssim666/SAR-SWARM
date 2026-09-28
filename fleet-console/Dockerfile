# syntax=docker/dockerfile:1
# Console image: the static build served by Caddy, which also proxies the API
# (the Caddyfile is mounted from deploy/ by compose).

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv/console
EXPOSE 80 443
