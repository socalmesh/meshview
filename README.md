
# Meshview
![Start Page](screenshots/animated.gif)

The project serves as a real-time monitoring and diagnostic tool for the Meshtastic mesh network. It provides detailed insights into the network's activity, including message traffic, node positions, and telemetry data.

### Version 2.0.3 update - June 2025
* Moved more graphs to eCharts.
* Addedd smooth updating for "Conversations" and "See everything" sections.
* Now you can turn on and off "Quick Links".
* Network graphs are now dynamically generated depending on your mesh and the presets in use.
* Download node's packet information for the last 3 days to .csv file.
* Display distance traveled by packet.
### Key Features

* **Live Data Visualization**: Users can view real-time data from the mesh network, including text messages, GPS positions, and node information.

* **Interactive Map**: The site offers an interactive map displaying the locations of active nodes, helping users identify network coverage areas.

* **Mesh Graphs**: Visual representations of the network's structure and connectivity are available, illustrating how nodes are interconnected.

* **Packet Analysis**: Detailed information on individual data packets transmitted within the network can be accessed, including payload content and transmission paths.

* **Node Statistics**: Users can explore statistics related to network traffic, such as top contributors and message volumes.

Samples of currently running instances:

- https://meshview.bayme.sh   (SF Bay Area)
- https://www.svme.sh/ (Sacramento Valley)
- https://meshview.nyme.sh/   (New York)
- https://map.wpamesh.net/ (Western Pennsylvania)
- https://meshview.chicagolandmesh.org/ (Chicago)
- https://meshview.mt.gt (Canadaverse)
- https://meshview.meshtastic.es (Spain)
- https://view.mtnme.sh/ (North Georgia / East Tennessee)
- https://socalmesh.w4hac.com  (Southern California)
- https://view.azmsh.net  (Arizona)
- https://meshview.aero-gaming.de/ (Hessen - Germany)

---

## Installing

Requires **`python3.11`** or above.

Clone the repo from GitHub:

```bash
git clone --recurse-submodules https://github.com/pablorevilla-meshtastic/meshview.git
```

> **NOTE**  
> It is important to include the `--recurse-submodules` flag or the meshtastic protobufs won't be included.

Create a Python virtual environment:

```bash
cd meshview
python3 -m venv env
```

Install the environment requirements:

```bash
./env/bin/pip install -r requirements.txt
```

Install `graphviz`:

```bash
sudo apt-get install graphviz
```

Copy `sample.config.ini` to `config.ini`:

```bash
cp sample.config.ini config.ini
```

Edit `config.ini` to match your MQTT and web server settings:

```bash
nano config.ini
```

Example:

```ini
# -------------------------
# Server Configuration
# -------------------------
[server]
# The address to bind the server to. Use * to listen on all interfaces.
bind = *

# Port to run the web server on.
port = 8081

# Path to TLS certificate (leave blank to disable HTTPS).
tls_cert =

# Path for the ACME challenge if using Let's Encrypt.
acme_challenge = /.well-known/acme-challenge


# -------------------------
# Site Appearance & Behavior
# -------------------------
[site]
# The domain name of your site.
domain =

# Site title to show in the browser title bar and headers.
title = Bay Area Mesh

# A brief message shown on the homepage.
message = Real time data from around the bay area and beyond.

# Enable or disable site features (as strings: "True" or "False").
nodes = True
conversations = True
everything = True
graphs = True
stats = True
net = True
map = True
top = True

# Map boundaries (used for the map view).
map_top_left_lat = 39
map_top_left_lon = -123
map_bottom_right_lat = 36
map_bottom_right_lon = -121

# Weekly net details
weekly_net_message = Weekly Mesh check-in. We will keep it open on every Wednesday from 5:00pm for checkins. The message format should be (LONG NAME) - (CITY YOU ARE IN) #BayMeshNet.
net_tag = #BayMeshNet


# -------------------------
# MQTT Broker Configuration
# -------------------------
[mqtt]
# MQTT server hostname or IP.
server = mqtt.bayme.sh

# Topics to subscribe to (as JSON-like list, but still a string).
topics = ["msh/US/bayarea/#", "msh/US/CA/mrymesh/#", "msh/US/CA/sacvalley/#"]

# Port used by MQTT (typically 1883 for unencrypted).
port = 1883

# MQTT username and password.
username = meshdev
password = large4cats


# -------------------------
# ACME/Let's Encrypt Configuration
# -------------------------
[acme]
# Enable ACME certificate management
enabled = False

# Email address for Let's Encrypt account registration
email = 

# Domain name for the certificate (without https://)
domain = 

# Path to store the certificate file
cert_path = cert.pem

# Path to store the private key file
key_path = key.pem

# Use staging server for testing (True/False)
staging = True

# Days before expiry to renew certificate
renewal_threshold_days = 30

# -------------------------
# Database Configuration
# -------------------------
[database]
# SQLAlchemy connection string. This one uses SQLite with asyncio support.
connection_string = sqlite+aiosqlite:///packets.db
```

---

## Running Meshview

Start the database:

```bash
./env/bin/python startdb.py
```

Start the web server:

```bash
./env/bin/python main.py
```

> **NOTE**  
> You can specify a custom config file with the `--config` flag:
>
> ```bash
> ./env/bin/python startdb.py --config /path/to/config.ini
> ./env/bin/python main.py --config /path/to/config.ini
> ```

Open in your browser: http://localhost:8081/

---

## SSL/HTTPS with Let's Encrypt

MeshView supports automatic SSL certificate management using Let's Encrypt, optimized for containerized environments.

### Setup

1. **Install dependencies**:
   ```bash
   pip install acme cryptography certbot
   ```

2. **Configure in config.ini**:
   ```ini
   [acme]
   enabled = True
   email = your-email@example.com
   domain = your-domain.com
   ```

3. **Run the application** - certificates are obtained automatically on startup.

### How It Works

- **Automatic startup certificates**: Always obtains new certificates on startup
- **HTTP-01 challenges**: Handled via aiohttp routes
- **Background renewal**: Checks and renews every 6 hours
- **Retry logic**: Built-in retry with exponential backoff
- **Container optimized**: Perfect for ephemeral containers

### Requirements

- **Port 80**: Required for HTTP-01 challenges
- **Domain resolution**: Your domain must point to the container
- **Let's Encrypt limits**: 50 certificates per week per domain

---

## Running Meshview with `mvrun.py`

- `mvrun.py` starts both `startdb.py` and `main.py` in separate threads and merges the output.
- It accepts the `--config` argument like the others.

```bash
./env/bin/python mvrun.py
```

---

## Setting Up Systemd Services (Ubuntu)

To run Meshview automatically on boot, create systemd services for `startdb.py` and `main.py`.
> **NOTE**  
> You need to change the "User" and "/path/to/meshview" for your instance of the code on each service.

### 1. Service for `startdb.py`

Create:

```bash
sudo nano /etc/systemd/system/meshview-db.service
```

Paste:

```ini
[Unit]
Description=Meshview Database Initializer
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/meshview
ExecStart=/path/to/meshview/env/bin/python /path/to/meshview/startdb.py --config /path/to/meshview/config.ini
Restart=always
RestartSec=5
User=yourusername

[Install]
WantedBy=multi-user.target
```

### 2. Service for `main.py`

Create:

```bash
sudo nano /etc/systemd/system/meshview-web.service
```

Paste:

```ini
[Unit]
Description=Meshview Web Server
After=network.target meshview-db.service

[Service]
Type=simple
WorkingDirectory=/path/to/meshview
ExecStart=/path/to/meshview/env/bin/python /path/to/meshview/main.py --config /path/to/meshview/config.ini
Restart=always
RestartSec=5
User=yourusername

[Install]
WantedBy=multi-user.target
```

### 3. Enable and start the services

```bash
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable meshview-db
sudo systemctl enable meshview-web
sudo systemctl start meshview-db
sudo systemctl start meshview-web
```

### 4. Check status

```bash
systemctl status meshview-db
systemctl status meshview-web
```

**TIP**  
After editing `.service` files, always run:

```bash
sudo systemctl daemon-reload
```

## 5. Database Maintenance
- Create and save bash script below. (Modify /path/to/file/ to the correct path)
- Name it cleanup.sh
- Make it executable.
```bash
 #!/bin/bash

DB_FILE="/path/to/file/packets.db"


# Stop DB service
sudo systemctl stop meshview-db.service
sudo systemctl stop meshview-web.service

sleep 5
echo "Run cleanup..."
# Run cleanup queries
sqlite3 "$DB_FILE" <<EOF 
DELETE FROM packet WHERE import_time < datetime('now', '-14 day');
DELETE FROM packet_seen WHERE import_time < datetime('now', '-14 day');
DELETE FROM traceroute WHERE import_time < datetime('now', '-14 day');
DELETE FROM node WHERE last_update < datetime('now', '-14 day') OR last_update IS NULL OR last_update = '';
VACUUM;
EOF

# Start DB service
sudo systemctl start meshview-db.service
sudo systemctl start meshview-web.service

echo "Database cleanup completed on $(date)"

```
- Schedule running the script on a regular basis. 
- In this example it runs every night at 2:00am.

Open scheduler:
```bash
sudo crontab -e
```
Add schedule to the bottom of the file (modify /path/to/file/ to the correct path):
```bash
0 2 * * * /path/to/file/cleanup.sh >> /path/to/file/cleanup.log 2>&1
```

Check the log file to see it the script run at the specific time.


