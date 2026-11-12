FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Expects the extract files in data/raw/ (mount them or copy them before building).
CMD ["sh", "-c", "python -m pipeline.run --skip-ai && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
