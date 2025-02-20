# Meshview

This project watches a MQTT topic for meshtastic messages, imports them to a
database and has a web UI to view them.

An example of a currently running instace for the San Francisco Bay Area mesh runs at https://meshview.bayme.sh

Requires **`python3.12`** and **`graphviz`**.

## Preparing

Clone the repo from github with:
``` bash 
git clone --recurse-submodules https://github.com/pablorevilla-meshtastic/meshview.git
```
> [!NOTE]
> It is important to include the `--recurse-submodules` flag or the meshtastic protobufs won't be included.

Create a python virtual environment:
``` bash
cd meshview
```
``` bash
python3 -m venv env
```
Install the environment requirements:
``` bash
./env/bin/pip install -r requirements.txt
```
You also need to install `graphviz`:
``` bash
sudo apt-get install graphviz
```
Edit `config.ini` to change the MQTT server, username, password, and topic(s) as necessary. 

You may also change the web server port from the ***default 8081***.
https://github.com/pablorevilla-meshtastic/meshview/blob/20bc89a21feb23b0dde51e10e21638c11f4e4443/config.ini#L1-L15

## Running Meshview

``` bash
./env/bin/python main.py
```
Now you can hit http://localhost:8081/
