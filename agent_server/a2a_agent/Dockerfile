# Use official Python image
FROM python:3.9-slim-bookworm

# Set working directory
WORKDIR /app

# Install dependencies first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port the app runs on
EXPOSE 80

# Start the application
CMD ["python", "main.py"]