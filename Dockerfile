# Используем официальный образ Python 3.12
FROM python:3.12-slim

# Устанавливаем системные зависимости для Playwright (нужны для запуска Chromium)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    libxshmfence1 \
    libnspr4 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libxrandr2 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnotify4 \
    libxss1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы с зависимостями
COPY requirements.txt .

# Устанавливаем Python-пакеты
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузеры Playwright
RUN playwright install chromium

# Копируем весь код проекта
COPY . .

# Открываем порт (обычно 8000)
EXPOSE 8000

# Команда запуска (используем uvicorn, без --reload в продакшне)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]