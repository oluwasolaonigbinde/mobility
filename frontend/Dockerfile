# Cardvert frontend — multi-stage production image.

FROM node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

FROM node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build
WORKDIR /app
ARG VCS_REF
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_RELEASE_REVISION=$VCS_REF
ARG NEXT_PUBLIC_SENTRY_DSN=""
ENV NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN
RUN npm run build

FROM node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS runtime
WORKDIR /app
ARG VCS_REF
LABEL org.opencontainers.image.title="Cardvert frontend" \
      org.opencontainers.image.revision="${VCS_REF}"
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Non-root runtime user
RUN addgroup -S cardvert && adduser -S cardvert -G cardvert
COPY --from=build --chown=cardvert:cardvert /app/.next/standalone ./
COPY --from=build --chown=cardvert:cardvert /app/.next/static ./.next/static
COPY --from=build --chown=cardvert:cardvert /app/public ./public
USER cardvert

EXPOSE 3000
CMD ["node", "server.js"]
