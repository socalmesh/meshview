import asyncio
import argparse
import configparser
import json
from meshview import mqtt_reader
from meshview import mqtt_database
from meshview import mqtt_store

async def load_database_from_mqtt(mqtt_server, mqtt_port, topics, mqtt_user=None, mqtt_passwd=None):
    async for received_topic, env in mqtt_reader.get_topic_envelopes(mqtt_server, mqtt_port, topics, mqtt_user, mqtt_passwd):
        await mqtt_store.process_envelope(received_topic, env)


async def run_daily(task_func, hour=0, minute=0):
    """Run an async task_func once every day at the specified hour and minute."""
    while True:
        from datetime import datetime, timedelta
        now_dt = datetime.now()
        target = now_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_dt:
            target += timedelta(days=1)
        delay = (target - now_dt).total_seconds()
        await asyncio.sleep(delay)

        try:
            await task_func()
        except Exception as e:
            print(f"Error during daily task: {e}")

async def main(config):
    mqtt_database.init_database(config["database"]["connection_string"])
    await mqtt_database.create_tables()

    mqtt_user = config["mqtt"]["username"] or None
    mqtt_passwd = config["mqtt"]["password"] or None
    mqtt_topics = json.loads(config["mqtt"]["topics"])

    async with asyncio.TaskGroup() as tg:
        tg.create_task(load_database_from_mqtt(
            config["mqtt"]["server"],
            int(config["mqtt"]["port"]),
            mqtt_topics,
            mqtt_user,
            mqtt_passwd
        ))
        # Schedule cleanup
        if config["database"]["cleanup"]:
            tg.create_task(run_daily(mqtt_store.cleanup_old_entries, hour=int(config["database"]["cleanup_hour"]), minute=int(config["database"]["cleanup_minutes"])))

def load_config(file_path):
    config_parser = configparser.ConfigParser()
    config_parser.read(file_path)
    return {section: dict(config_parser.items(section)) for section in config_parser.sections()}

if __name__ == '__main__':
    parser = argparse.ArgumentParser("meshview")
    parser.add_argument("--config", help="Path to the configuration file.", default='config.ini')
    args = parser.parse_args()
    config = load_config(args.config)
    asyncio.run(main(config))
