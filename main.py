import asyncio
import argparse
import configparser
from meshview import mqtt_reader
from meshview import database
from meshview import store
from meshview import web
from meshview import http


async def load_database_from_mqtt(mqtt_server, topic):
    async for topic, env in mqtt_reader.get_topic_envelopes(mqtt_server, topic):
        await store.process_envelope(topic, env)


async def main(config):
    database.init_database(config["database"]["connection_string"])

    await database.create_tables()
    async with asyncio.TaskGroup() as tg:
        tg.create_task(
            load_database_from_mqtt(config["mqtt"]["server"], config["mqtt"]["topics"].split(","))
        )
        tg.create_task(
            web.run_server(
                config["server"]["bind"],
                int(config["server"]["port"]),
                config["server"].get("tls_cert"),
            )
        )
        if config["server"].get("acme_challenge"):
            tg.create_task(
                http.run_server(
                    config["server"]["bind"], config["server"]["acme_challenge"]
                )
            )


def load_config(file_path):
    """Load configuration from an INI-style text file."""
    config_parser = configparser.ConfigParser()
    config_parser.read(file_path)

    # Convert to a dictionary for easier access
    config = {section: dict(config_parser.items(section)) for section in config_parser.sections()}
    return config


if __name__ == '__main__':
    parser = argparse.ArgumentParser("meshview")
    parser.add_argument("--config", help="Path to the configuration file.", default='config.ini')
    args = parser.parse_args()

    config = load_config(args.config)

    asyncio.run(main(config))