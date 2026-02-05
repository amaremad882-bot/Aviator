FROM python:3.11-slim

WORKDIR /app

# نسخ ملفات المشروع
COPY requirements.txt .
COPY main.py .
COPY config.py .
COPY database.py .
COPY game_logic.py .
COPY nixpacks.toml .
COPY railway.json .
COPY runtime.txt .

# تثبيت الاعتماديات
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# فتح المنفذ
EXPOSE 8000

# تشغيل التطبيق
CMD ["python", "main.py"]