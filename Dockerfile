# Dockerfile pour BotDoctor + API + Dashboard
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip \
    && pip install fastapi uvicorn streamlit pandas requests pytest flake8 black

EXPOSE 8008 8501

CMD ["sh", "-c", "uvicorn supervision.botdoctor_api:app --host 0.0.0.0 --port 8008 & streamlit run supervision/botdoctor_dashboard.py --server.port 8501"]
