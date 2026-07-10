FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agents/ ./agents/
EXPOSE 8002
CMD ["uvicorn", "agents.deploy_status.api:app", "--host", "0.0.0.0", "--port", "8002"]