# Use an official Python runtime as the base image
FROM python:3.12-slim

# Build-time version injected by CI (fallback for local builds)
ARG APP_VERSION=0.0.0-dev

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install OS dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

# Install the required packages
RUN pip install -r requirements.txt --no-cache-dir

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable
ENV FLASK_APP=run.py
ENV APP_VERSION=${APP_VERSION}

# Run the application using Gunicorn with TLS enabled on port 5000
RUN chmod +x /app/docker/start-gunicorn.sh
CMD ["/app/docker/start-gunicorn.sh"]
