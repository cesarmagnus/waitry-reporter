FROM python:3.12-slim

# Instalar dependencias del sistema para Chromium en Debian Trixie
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxcb1 libxkbcommon0 libx11-6 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libatspi2.0-0 \
    libx11-xcb1 libxcb-dri3-0 \
    fonts-liberation fonts-dejavu fonts-unifont \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium sin --with-deps (las dependencias ya están instaladas arriba)
RUN playwright install chromium

# Copiar código
COPY . .

ENV TZ=America/Santiago

CMD ["python", "main.py"]
