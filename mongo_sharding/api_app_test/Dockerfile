FROM python:3.11-slim

WORKDIR /tests

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app_test.py .

CMD ["pytest", "app_test.py", "-v", "--tb=short", "--color=yes"]

