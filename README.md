Meshview
========

Now running at https://meshview.bayme.sh

This project watches a MQTT topic for meshtastic messages, imports them to a
database and has a web UI to view them.
Requires Python 3.12

Running
-------
Clone the repo from github with:
``` bash 
git clone --recurse-submodules https://github.com/pablorevilla-meshtastic/meshview.git
```
It is important to include the `--recurse-submodule` flag or the meshtastic protobufs wont be included

Create a python virtual environment:
``` bash
cd meshview
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

To run Meshview:
``` bash
./env/bin/python main.py
```
Now you can hit http://localhost/

Other Options:
* `--port`

   Web server port, default is `8081`

* `--mqtt-server`

  MQTT Server, default is `mqtt.bayme.sh`

* `--topic`
    
  MQTT Topic, default is `msh/US/bayarea/#`

