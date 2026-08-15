FROM python:3.12-slim
WORKDIR /app
COPY backend/pyproject.toml /tmp/pyproject.toml
RUN pip install --no-cache-dir $(python -c "import tomllib; print(' '.join(tomllib.load(open('/tmp/pyproject.toml','rb'))['project']['dependencies']))")
COPY backend /app
ENV PYTHONPATH=/app
