FROM ubuntu:latest

# Install system dependencies
RUN apt-get update && \
    apt-get install -y wget git graphviz && \
    rm -rf /var/lib/apt/lists/*

# Install Miniconda
ENV PATH="/opt/conda/bin:$PATH"
RUN wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /miniconda.sh && \
    bash /miniconda.sh -b -p /opt/conda && \
    rm /miniconda.sh

# Set work directory
WORKDIR /app

# Clone the repository with submodules
RUN git clone --recurse-submodules https://github.com/pablorevilla-meshtastic/meshview.git /app

# Create conda environment
RUN conda create -n meshview python=3.11 -y

# Activate environment and install dependencies
RUN /opt/conda/envs/meshview/bin/pip install -r /app/requirements.txt

#place sample config in place
RUN cp /app/sample.config.ini /app/config.ini

#change default to 8000
RUN sed -ie 's/port = 8081/port = 8000/g' /app/config.ini

# Expose the web server port
EXPOSE 8000

# Copy start.sh into container
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Start the application using the conda environment
CMD ["/app/start.sh"]