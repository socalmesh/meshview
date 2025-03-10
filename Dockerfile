# Use the official Python base image with dependencies installed.
FROM python:3.11-bookworm

# Install Graphviz
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code to the container
COPY . .

# Ensure the /data directory exists
RUN mkdir -p /data

# Expose the port the application listens on
EXPOSE 8000

#expose the endpoint to create a persistent database. Note this is not compatible with Azure Files SMB, only NFS. Not implemented currrently.
VOLUME /data

# Start the database and then the application
CMD ["sh", "-c", "python startdb.py && python main.py"]
