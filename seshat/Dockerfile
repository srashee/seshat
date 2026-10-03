# Supervisor versions may supply an Alpine BUILD_FROM override. Seshat needs
# Debian's glibc for the pinned OpenCV wheels, so select the base explicitly.
FROM python:3.12.14-slim-bookworm AS builder
WORKDIR /build
COPY requirements.txt models.lock.json ./
COPY scripts ./scripts
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt \
    && python scripts/download_models.py --output /models

FROM python:3.12.14-slim-bookworm
ARG BUILD_VERSION=1.1.0
ARG BUILD_ARCH=amd64
LABEL io.hass.version="${BUILD_VERSION}" io.hass.type="app" io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.title="Seshat" org.opencontainers.image.version="${BUILD_VERSION}"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
WORKDIR /opt/seshat
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-cache-dir --no-index --find-links /wheels -r requirements.txt && rm -rf /wheels
COPY --from=builder /models /opt/models
COPY app ./app
COPY run.sh /run.sh
RUN chmod 755 /run.sh
EXPOSE 8000 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["/run.sh"]
