# STRETCH GOAL 4: runs the tests by default; README "Test" shows how to run the app with a data volume.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["pytest"]
