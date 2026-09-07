FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[dev]"

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]