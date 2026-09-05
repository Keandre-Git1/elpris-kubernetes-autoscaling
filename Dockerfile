# Steg 1: Bygg beroenden
# Bygger i ett separat steg så att build-verktyg (pip behöver
# ibland gcc etc för paket som pandas/numpy) inte hamnar i slutimagen.
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
# --prefix=/install gör att vi kan kopiera ENDAST de installerade paketen
# till slutimagen i nästa steg, utan pip/cache/build-verktyg.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Steg 2: Den faktiska image som körs
FROM python:3.12-slim

# Kör som en icke-root-användare. Om containern blir komprometterad (t.ex.
# via ett sårbart beroende) begränsar det här vad en angripare kan göra.
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Kopiera in de färdiginstallerade paketen från builder-steget
COPY --from=builder /install /usr/local

# Kopiera bara det appen faktiskt behöver (se .dockerignore för resten)
COPY application/ ./application/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 2800

# Låter Docker/Kubernetes fråga "mår appen bra?" utan extra verktyg.
# Använder python istället för curl eftersom curl inte är installerat
# i python:3.12-slim (och vi vill hålla imagen liten).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2800/health', timeout=2)" || exit 1

# gunicorn istället för 'flask run' för att Flasks inbyggda server är explicit
CMD ["gunicorn", "--bind", "0.0.0.0:2800", "--workers", "2", "application.app:app"]
