FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir -U pip setuptools wheel

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY entrypoint.sh ./entrypoint.sh

RUN chmod +x /app/entrypoint.sh
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh","/app/entrypoint.sh"]
