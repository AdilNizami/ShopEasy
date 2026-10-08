FROM python:3.12-slim

ARG SERVICE_PACKAGE
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVICE_PACKAGE=${SERVICE_PACKAGE} \
    PYTHONPATH=/app/services/${SERVICE_PACKAGE}:/app/services/common

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY services /app/services
COPY contracts/events /app/contracts/events
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
USER app
EXPOSE 8000
CMD ["sh", "-c", "if [ \"$SERVICE_PACKAGE\" != gateway ]; then python -m ${SERVICE_PACKAGE}.infrastructure.init_db; fi; uvicorn ${SERVICE_PACKAGE}.main:app --host 0.0.0.0 --port 8000"]
