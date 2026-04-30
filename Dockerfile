FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY classifier.py .
COPY main.py .

EXPOSE ${PORT:-8000}

# Use shell form so $PORT is expanded at runtime (Railway injects $PORT)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
