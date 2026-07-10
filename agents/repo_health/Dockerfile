FROM python:3.13-slim

WORKDIR /app

# Copy only what this service needs, in dependency order (best layer-caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole project (agents/ needs to be importable as a package)
COPY agents/ ./agents/

EXPOSE 8001

CMD ["uvicorn", "agents.repo_health.api:app", "--host", "0.0.0.0", "--port", "8001"]