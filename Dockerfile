# Use a slim Python base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8080

# Set working directory
WORKDIR /app

# Install python dependencies directly using pip
RUN pip install --no-cache-dir \
    "fastapi>=0.110.0" \
    "uvicorn>=0.28.0" \
    "pydantic>=2.0.0" \
    "fastmcp>=0.1.0" \
    "google-adk[gcp]==2.2.0" \
    "google-genai" \
    "requests" \
    "jinja2" \
    "python-multipart"

# Copy the agent and dashboard code
COPY aegismed-agent/ /app/aegismed-agent/
COPY dashboard/ /app/dashboard/

# Expose port
EXPOSE 8080

# Command to run the application
CMD ["python", "dashboard/main.py"]
