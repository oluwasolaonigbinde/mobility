# Vantage frontend — multi-stage production image.
# Build:  docker build -t vantage-frontend ./frontend
# Run:    docker run -p 3000:3000 -e API_BASE_URL=http://api:8000 vantage-frontend

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_SENTRY_DSN=""
ENV NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Non-root runtime user
RUN addgroup -S vantage && adduser -S vantage -G vantage
COPY --from=build --chown=vantage:vantage /app/.next/standalone ./
COPY --from=build --chown=vantage:vantage /app/.next/static ./.next/static
COPY --from=build --chown=vantage:vantage /app/public ./public
USER vantage

EXPOSE 3000
CMD ["node", "server.js"]
