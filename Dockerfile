FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-production.txt ./
RUN pip install --no-cache-dir --timeout 600 --retries 10 \
        --require-hashes -r requirements-production.txt \
    && groupadd --system cardvert \
    && useradd --system --gid cardvert --home-dir /nonexistent --shell /usr/sbin/nologin cardvert

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

ARG VCS_REF
LABEL org.opencontainers.image.title="Cardvert API" \
      org.opencontainers.image.revision="${VCS_REF}"

USER cardvert

EXPOSE 8000

# uvicorn's --workers defaults to $WEB_CONCURRENCY; override it at run time.
ENV WEB_CONCURRENCY=2

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
