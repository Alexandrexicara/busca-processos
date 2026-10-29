FROM python:3.11-slim

WORKDIR /app

# Dependências de sistema e navegador Chromium para Playwright.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8000
ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["python", "main.py"]
