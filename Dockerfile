FROM python@sha256:be8ccd085666c34273c9dc5607c9842f8b2e3116128aae45148ce164c07ce09d

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
