FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN mkdir /app
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN apt update && apt install -y netcat-openbsd && apt install -y --no-install-recommends exiftool libimage-exiftool-perl
COPY requirements.txt pyproject.toml uv.lock /app/
RUN uv pip install --system -r requirements.txt
COPY . /app/
EXPOSE 8000
CMD ["python", "main.py"]
