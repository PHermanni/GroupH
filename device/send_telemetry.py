
"""Send telemetry to Azure IoT Hub with a persistent local SQLite queue."""

import json
import logging
import os
import random
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from azure.iot.device import IoTHubDeviceClient, Message

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("iot-device")

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "telemetry.db"
RETRY_BASE_SECONDS = 2
RETRY_MAX_SECONDS = 60
SEND_BATCH_SIZE = 20


def read_sensor():
    """Return simulated temperature and humidity readings."""
    return (
        round(random.uniform(19.0, 26.0), 2),
        round(random.uniform(30.0, 65.0), 2),
    )


def open_queue(db_path=None):
    """Open and initialize the persistent local measurement queue."""
    path = Path(
        db_path or os.getenv("TELEMETRY_DB_PATH", str(DEFAULT_DB_PATH))
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(path), timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def enqueue_measurement(connection, payload):
    """Save a measurement locally before attempting transmission."""
    connection.execute(
        """
        INSERT INTO telemetry_queue (payload, created_at)
        VALUES (?, ?)
        """,
        (
            json.dumps(payload, separators=(",", ":")),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    connection.commit()


def queued_count(connection):
    """Return the number of measurements waiting to be sent."""
    return connection.execute(
        "SELECT COUNT(*) FROM telemetry_queue"
    ).fetchone()[0]


def send_pending(client, connection, batch_size=SEND_BATCH_SIZE):
    """Send queued measurements oldest-first, retaining failed messages."""
    rows = connection.execute(
        """
        SELECT id, payload
        FROM telemetry_queue
        ORDER BY id
        LIMIT ?
        """,
        (batch_size,),
    ).fetchall()

    sent = 0

    for row_id, raw_payload in rows:
        try:
            message = Message(raw_payload)
            message.content_type = "application/json"
            message.content_encoding = "utf-8"
            client.send_message(message)
        except Exception:
            log.warning(
                "Could not send queued measurement id=%s; keeping it.",
                row_id,
                exc_info=True,
            )
            # Stop this batch; retry later rather than rapidly retrying.
            break
        else:
            connection.execute(
                "DELETE FROM telemetry_queue WHERE id = ?",
                (row_id,),
            )
            connection.commit()
            sent += 1

    return sent


def main():
    connection_string = os.getenv("IOTHUB_DEVICE_CONNECTION_STRING")
    if not connection_string:
        raise SystemExit(
            "Set IOTHUB_DEVICE_CONNECTION_STRING before running."
        )

    device_id = os.getenv("DEVICE_ID", "raspberrypi-01")
    interval = max(5, int(os.getenv("SAMPLE_INTERVAL_SECONDS", "60")))
    retry_delay = RETRY_BASE_SECONDS
    client = None

    # Open the durable queue even if Azure is initially unavailable.
    with open_queue() as queue:
        try:
            try:
                client = IoTHubDeviceClient.create_from_connection_string(
                    connection_string
                )
                client.connect()
                log.info(
                    "Connected as %s; sampling every %s seconds.",
                    device_id,
                    interval,
                )
            except Exception:
                log.warning(
                    "Initial IoT Hub connection failed; data will be queued.",
                    exc_info=True,
                )

            while True:
                temperature, humidity = read_sensor()

                payload = {
                    "device_id": device_id,
                    "temperature_c": temperature,
                    "humidity_percent": humidity,
                    "measured_at": datetime.now(timezone.utc).isoformat(),
                }

                # Always save locally first.
                enqueue_measurement(queue, payload)
                log.info(
                    "Measurement queued: temperature=%s C, humidity=%s %%, "
                    "queue_size=%s",
                    temperature,
                    humidity,
                    queued_count(queue),
                )

                if client is None:
                    try:
                        client = (
                            IoTHubDeviceClient.create_from_connection_string(
                                connection_string
                            )
                        )
                        client.connect()
                        log.info("IoT Hub connection established.")
                        retry_delay = RETRY_BASE_SECONDS
                    except Exception:
                        log.warning(
                            "IoT Hub unavailable; measurements remain queued."
                        )
                        time.sleep(retry_delay)
                        retry_delay = min(
                            retry_delay * 2, RETRY_MAX_SECONDS
                        )
                        continue

                sent = send_pending(client, queue)

                if sent:
                    log.info(
                        "Sent %s measurement(s); remaining=%s",
                        sent,
                        queued_count(queue),
                    )
                    retry_delay = RETRY_BASE_SECONDS

                if queued_count(queue):
                    # Keep collecting while retrying with increasing delays.
                    time.sleep(retry_delay)
                    retry_delay = min(
                        retry_delay * 2, RETRY_MAX_SECONDS
                    )
                else:
                    time.sleep(interval)
                    retry_delay = RETRY_BASE_SECONDS

        except KeyboardInterrupt:
            log.info("Stopped by user.")
        finally:
            if client is not None:
                try:
                    client.shutdown()
                except Exception:
                    log.warning(
                        "Error shutting down IoT Hub client.",
                        exc_info=True,
                    )


if __name__ == "__main__":
    main()
