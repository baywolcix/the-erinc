# BULUT HOME — Debian tabanlı hafif imaj (ASUS i3 / 8 GB RAM hedefi)
FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    BULUT_DATA_DIR=/data BULUT_ENV_FILE=/nonexistent

RUN useradd --create-home --uid 1000 bulut
WORKDIR /srv/bulut
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN mkdir -p /data && chown bulut:bulut /data
USER bulut
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=4).status==200 else 1)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers"]
