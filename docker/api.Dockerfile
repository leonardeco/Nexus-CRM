FROM python:3.12-slim
WORKDIR /app
COPY backend/pyproject.toml /tmp/pyproject.toml
RUN pip install --no-cache-dir fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic redis argon2-cffi pyotp pydantic-settings email-validator httpx pytest pytest-asyncio
COPY backend /app
ENV PYTHONPATH=/app
