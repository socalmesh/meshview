FROM continuumio/miniconda3:latest

# Install system dependencies including certbot, sqlite3, and cron
RUN apt-get update && \
    apt-get install -y wget git graphviz python3-certbot-apache sqlite3 cron && \
    rm -rf /var/lib/apt/lists/*

# Create conda environment
RUN conda create -n meshview python=3.11 -y

# Set work directory
WORKDIR /app

# Copy local files instead of cloning from GitHub
COPY . /app

# Activate environment and install dependencies
RUN /opt/conda/envs/meshview/bin/pip install -r /app/requirements.txt

# Copy and set up cleanup script
COPY cleanup.sh /app/cleanup.sh
RUN chmod +x /app/cleanup.sh

# Set up cron job for database cleanup (runs every night at 2 AM)
RUN echo "0 2 * * * /app/cleanup.sh >> /app/cleanup.log 2>&1" | crontab -

# Copy start.sh into container
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

#place sample config in place
#RUN cp /app/sample.config.ini /app/config.ini

#change default to 8000
#RUN sed -ie 's/port = 8081/port = 8000/g' /app/config.ini

# Expose the web server port
EXPOSE 8000

# Start the application using the conda environment
CMD ["/app/start.sh"]
