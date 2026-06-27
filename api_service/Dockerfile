# ---- Base image ----
FROM python:3.11-slim

# ---- Set workdir ----
WORKDIR /app

# ---- Install system deps ----
RUN apt-get update && apt-get install -y \
    build-essential \
    && apt-get clean

# ---- Copy requirements ----
COPY requirements.txt .

# ---- Install Python deps ----
RUN pip install --no-cache-dir -r requirements.txt

# ---- Copy application ----
COPY . .


# ---- Expose port ----
EXPOSE 8888

# ---- Run server ----
CMD ["uvicorn", "main:fastapi_app", "--host", "0.0.0.0", "--port", "8888"]


#CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]