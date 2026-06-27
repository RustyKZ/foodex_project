

#FROM python:3.11-slim
#WORKDIR /app
#COPY requirements.txt .
#RUN pip install --no-cache-dir -r requirements.txt
#COPY . .
#ENV PYTHONUNBUFFERED=1 \
#    DJANGO_SETTINGS_MODULE=foodex_admin.settings
#CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]


FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
ENV PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=foodex_admin.settings
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["gunicorn", "foodex_admin.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]