# Use official Python image
FROM python:3.13-slim-bookworm

# Install curl, gnupg, and Node.js 18 (includes npx)
RUN apt-get update && apt-get install -y curl gnupg ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Check versions
RUN node --version && npm --version && npx --version

# Set working directory
WORKDIR /app

# Install dependencies first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Start the application
CMD ["python", "main.py"]