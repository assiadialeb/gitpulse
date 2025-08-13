FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install minimal system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        g++ \
        gcc \
        git \
        libpq-dev \
        netcat-traditional \
        wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Python dependencies and setup project
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project and setup
COPY . .
RUN mkdir -p /app/data /app/logs \
    && chmod +x start.sh \
    && python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Run the application
CMD ["./start.sh"]