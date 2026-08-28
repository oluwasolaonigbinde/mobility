FROM python@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217

ARG VCS_REF
LABEL org.opencontainers.image.title="Cardvert API" \
      org.opencontainers.image.revision="${VCS_REF}"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-production.txt ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir --require-hashes -r requirements-production.txt \
    && groupadd --system cardvert \
    && useradd --system --gid cardvert --home-dir /nonexistent --shell /usr/sbin/nologin cardvert

USER cardvert

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
