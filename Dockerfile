FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY src ./src

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:8080", "--chdir", "src", "main:app"]
