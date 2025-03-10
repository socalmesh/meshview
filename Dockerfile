# Use the official Python base image with dependencies installed.
FROM python:3.11-bookworm

# Install required dependencies (Git, Graphviz)
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the entire repository into the container (including submodules)
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Ensure the /data directory exists
RUN mkdir -p /data

# Expose the port the application listens on
EXPOSE 8000

# Declare a volume for persistent storage
VOLUME /data

# Start the database and then the application
CMD ["sh", "-c", "python startdb.py --config /app/config.ini && python main.py --config /app/config.ini"]
