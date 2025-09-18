import asyncio
import json
import datetime
import logging
import aiosqlite
from meshview import mqtt_reader
from meshview import mqtt_database
from meshview import mqtt_store
from meshview.config import CONFIG  # <-- use your existing config.py

# -------------------------
# Logging for cleanup
# -------------------------
cleanup_logger = logging.getLogger("dbcleanup")
cleanup_logger.setLevel(logging.INFO)
file_handler = logging.FileHandler("dbcleanup.log")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
file_handler.setFormatter(formatter)
cleanup_logger.addHandler(file_handler)

# -------------------------
# Helper functions
# -------------------------
def get_bool(config, section, key, default=False):
    return config.get(section, {}).get(key, str(default)).lower() in ("1", "true", "yes", "on")

def get_int(config, section, key, default=0):
    try:
        return int(config.get(section, {}).get(key, default))
    except ValueError:
        return default

# -------------------------
# Database cleanup using aiosqlite with batching
# -------------------------
async def daily_cleanup_at(db_file: str, hour: int = 2, minute: int = 0, days_to_keep: int = 14, vacuum_db: bool = True, batch_size: int = 100):
    tables = {
        "packet": "import_time",
        "packet_seen": "import_time",
        "traceroute": "import_time",
        "node": "last_update"
    }

    while True:
        now = datetime.datetime.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += datetime.timedelta(days=1)
        delay = (next_run - now).total_seconds()
        cleanup_logger.info(f"Next cleanup scheduled at {next_run}")
        await asyncio.sleep(delay)

        try:
            cleanup_logger.info(f"Running cleanup for records older than {days_to_keep} days...")

            async with aiosqlite.connect(db_file) as db:
                for table, time_column in tables.items():
                    total_deleted = 0  # Initialize total counter
                    while True:
                        if table == "node":
                            query = f"""
                                DELETE FROM node
                                WHERE {time_column} < datetime('now', '-{days_to_keep} day')
                                   OR {time_column} IS NULL
                                   OR {time_column} = ''
                                LIMIT {batch_size};
                            """
                        else:
                            query = f"""
                                DELETE FROM {table}
                                WHERE {time_column} < datetime('now', '-{days_to_keep} day')
                                LIMIT {batch_size};
                            """
                        cursor = await db.execute(query)
                        await db.commit()
                        deleted = cursor.rowcount or 0
                        total_deleted += deleted
                        if deleted == 0:
                            break
                        await asyncio.sleep(0)  # yield to event loop

                    cleanup_logger.info(f"Deleted a total of {total_deleted} rows from {table}")

            if vacuum_db:
                async with aiosqlite.connect(db_file) as db:
                    await db.execute("VACUUM;")

            cleanup_logger.info("Cleanup completed successfully.")

        except Exception as e:
            cleanup_logger.error(f"Error during cleanup: {e}")


# -------------------------
# MQTT loading
# -------------------------
async def load_database_from_mqtt(mqtt_server: str, mqtt_port: int, topics: list, mqtt_user: str | None = None, mqtt_passwd: str | None = None):
    async for topic, env in mqtt_reader.get_topic_envelopes(mqtt_server, mqtt_port, topics, mqtt_user, mqtt_passwd):
        await mqtt_store.process_envelope(topic, env)

# -------------------------
# Main function
# -------------------------
async def main():
    # Initialize database
    mqtt_database.init_database(CONFIG["database"]["connection_string"])
    await mqtt_database.create_tables()

    mqtt_user = CONFIG["mqtt"].get("username") or None
    mqtt_passwd = CONFIG["mqtt"].get("password") or None
    mqtt_topics = json.loads(CONFIG["mqtt"]["topics"])

    db_file = CONFIG["database"]["connection_string"].replace("sqlite+aiosqlite:///", "")
    cleanup_enabled = get_bool(CONFIG, "cleanup", "enabled", False)
    cleanup_days = get_int(CONFIG, "cleanup", "days_to_keep", 14)
    vacuum_db = get_bool(CONFIG, "cleanup", "vacuum", False)
    cleanup_hour = get_int(CONFIG, "cleanup", "hour", 2)
    cleanup_minute = get_int(CONFIG, "cleanup", "minute", 0)
    batch_size = get_int(CONFIG, "cleanup", "batch_size", 100)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(
            load_database_from_mqtt(CONFIG["mqtt"]["server"], int(CONFIG["mqtt"]["port"]), mqtt_topics, mqtt_user, mqtt_passwd)
        )

        if cleanup_enabled:
            tg.create_task(
                daily_cleanup_at(db_file, cleanup_hour, cleanup_minute, cleanup_days, vacuum_db, batch_size)
            )
        else:
            cleanup_logger.info("Daily cleanup is disabled by configuration.")

# -------------------------
# Entry point
# -------------------------
if __name__ == '__main__':
    asyncio.run(main())
