FROM ubuntu:latest

# Install system dependencies including certbot, sqlite3, and cron
RUN apt-get update && \
    apt-get install -y wget git graphviz python3-certbot-apache sqlite3 cron && \
    rm -rf /var/lib/apt/lists/*

# Install Miniconda
ENV PATH="/opt/conda/bin:$PATH"
RUN wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /miniconda.sh && \
    bash /miniconda.sh -b -p /opt/conda && \
    rm /miniconda.sh

# Debug conda installation
RUN echo "Conda version:" && /opt/conda/bin/conda --version && \
    echo "Conda info:" && /opt/conda/bin/conda info

# Initialize conda and create environment
RUN /opt/conda/bin/conda init bash && \
    echo "Creating conda environment..." && \
    /opt/conda/bin/conda create -n meshview python=3.11 -y -v

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
