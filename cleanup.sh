#!/bin/bash

DB_FILE="/app/packets.db"

echo "Starting database cleanup on $(date)"

# Run cleanup queries
sqlite3 "$DB_FILE" <<EOF 
DELETE FROM packet WHERE import_time < datetime('now', '-14 day');
DELETE FROM packet_seen WHERE import_time < datetime('now', '-14 day');
DELETE FROM traceroute WHERE import_time < datetime('now', '-14 day');
DELETE FROM node WHERE last_update < datetime('now', '-14 day') OR last_update IS NULL OR last_update = '';
VACUUM;
EOF

echo "Database cleanup completed on $(date)" 