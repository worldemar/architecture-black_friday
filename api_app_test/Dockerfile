FROM python:3.11-slim

WORKDIR /tests

# Copy test requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy test files
COPY app_test.py .

# Run tests with verbose output
CMD ["pytest", "app_test.py", "-v", "--tb=short", "--color=yes"]

