FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-nube.txt .
RUN pip install --no-cache-dir -r requirements-nube.txt
COPY camtoshop camtoshop
CMD exec uvicorn camtoshop.web.app:app --host 0.0.0.0 --port ${PORT:-8080}
