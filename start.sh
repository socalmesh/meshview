#!/bin/bash

# Start cron in the background
cron

# Start the database and web services
/opt/conda/envs/meshview/bin/python /app/startdb.py --config /app/config.ini &
/opt/conda/envs/meshview/bin/python /app/main.py --config /app/config.ini &

wait