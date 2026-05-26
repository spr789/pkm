FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ app/

RUN pip install --no-cache-dir -e ".[ai]"

COPY . .

EXPOSE 8080

CMD ["python", "-m", "app.cloud_run"]
