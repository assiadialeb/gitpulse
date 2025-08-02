FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies and language runtimes for cdxgen
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev \
        netcat-traditional \
        # Java dependencies
        openjdk-11-jdk \
        maven \
        gradle \
        # Ruby dependencies
        ruby \
        ruby-bundler \
        ruby-dev \
        # Node.js dependencies
        nodejs \
        npm \
        # Go dependencies
        golang-go \
        # .NET dependencies
        dotnet-sdk-6.0 \
        # Additional tools
        git \
        curl \
        wget \
        unzip \
        # Clean up
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install cdxgen globally
RUN npm install -g @cyclonedx/cdxgen

# Install Ruby gems for cdxgen
RUN gem install bundler

# Copy project
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Make startup script executable
RUN chmod +x start.sh

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Run the application
CMD ["./start.sh"]