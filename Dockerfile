# STRETCH GOAL 4: runs the tests by default; run the app with `docker run IMAGE python main.py <command>`.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["pytest"]
