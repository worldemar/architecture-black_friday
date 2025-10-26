FROM python:3.11-slim

WORKDIR /workspace

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["ruff", "check", ".", "--config", "pyproject.toml"]
CMD []
