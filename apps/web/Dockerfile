# syntax=docker/dockerfile:1.7

# ============== base ==============
FROM node:20-alpine AS base
RUN corepack enable
WORKDIR /app

# ============== deps ==============
FROM base AS deps
COPY package.json ./
# create lockfile on first build inside the container
RUN pnpm install --no-frozen-lockfile

# ============== dev ==============
FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "3000"]

# ============== build ==============
FROM deps AS build
COPY . .
RUN pnpm build

# ============== prod ==============
FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY ../../infra/nginx/web.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost/ || exit 1
