# ベースイメージのバージョンと requirements.txt の playwright のバージョンは必ず一致させること
# ずれると Executable doesn't exist というエラーで起動しない
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
