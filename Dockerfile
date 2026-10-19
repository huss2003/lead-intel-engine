FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 DEMO_MODE=1 LIE_DB=/data/lie.db
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && mkdir /data
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "--factory", "lie.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
