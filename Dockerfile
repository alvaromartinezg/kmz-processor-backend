# Dockerfile
FROM python:3.11-slim

# Evita bytecode y buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Dependencias del sistema (si hiciera falta xml or zip ya vienen en stdlib)
RUN pip install --no-cache-dir --upgrade pip

# Requisitos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código + base
COPY main.py .
COPY informative-letters-v3.py .
COPY DATABASE.kmz .

# Expone el puerto estándar de Cloud Run
EXPOSE 8080

# Arranque del servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
