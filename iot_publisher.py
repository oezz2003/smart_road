"""MQTT publisher that glues the vision counts, planning algorithm, and IoT devices."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from typing import Dict

import paho.mqtt.client as mqtt

from algo_two_phase import Cycle, plan_cycle
from vision_select_and_count import count_stream

DEFAULT_BROKER = os.getenv("SMART_ROAD_BROKER", "broker.emqx.io")
DEFAULT_PORT = int(os.getenv("SMART_ROAD_PORT", "1883"))
TOPIC_CYCLE = os.getenv("SMART_ROAD_TOPIC_CYCLE", "signals/cycle")
TOPIC_CARS = {
    "N": os.getenv("SMART_ROAD_TOPIC_CAR_N", "cars/N"),
    "S": os.getenv("SMART_ROAD_TOPIC_CAR_S", "cars/S"),
    "E": os.getenv("SMART_ROAD_TOPIC_CAR_E", "cars/E"),
    "W": os.getenv("SMART_ROAD_TOPIC_CAR_W", "cars/W"),
}


class TrafficPublisher:
    def __init__(self, host: str, port: int, client_id: str | None = None) -> None:
        self.host = host
        self.port = port
        self.client = mqtt.Client(client_id=client_id or "smart-road-pub", clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.reconnect_delay_set(min_delay=1, max_delay=5)
        self.connected = threading.Event()
        self._stop = threading.Event()
        self.client.will_set(TOPIC_CYCLE, "CYCLE NS 5000 5000 2000 1000", qos=0, retain=False)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[mqtt] Connected to {self.host}:{self.port}")
            self.connected.set()
        else:
            print(f"[mqtt] Failed to connect (rc={rc})")

    def _on_disconnect(self, client, userdata, rc):
        self.connected.clear()
        if rc != 0:
            print(f"[mqtt] Unexpected disconnect (rc={rc}); will retry.")

    def start(self) -> None:
        self.client.connect_async(self.host, self.port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        try:
            for direction in TOPIC_CARS:
                self.client.publish(TOPIC_CARS[direction], "STOP", qos=1, retain=False)
        finally:
            self.client.loop_stop()
            self.client.disconnect()

    def publish_cycle(self, cycle: Cycle) -> bool:
        if not self.connected.wait(timeout=5):
            print("[mqtt] Still offline; skipping cycle publish.")
            return False
        payload = f"CYCLE {cycle.order} {cycle.ns_green_ms} {cycle.ew_green_ms} {cycle.amber_ms} {cycle.allred_ms}"
        result = self.client.publish(TOPIC_CYCLE, payload, qos=1, retain=False)
        result.wait_for_publish()
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"[mqtt] Failed to publish cycle (rc={result.rc})")
            return False
        if cycle.order == "NS":
            self._publish_car("N", f"GO {cycle.ns_green_ms}")
            self._publish_car("S", f"GO {cycle.ns_green_ms}")
            self._publish_car("E", "STOP")
            self._publish_car("W", "STOP")
        else:
            self._publish_car("E", f"GO {cycle.ew_green_ms}")
            self._publish_car("W", f"GO {cycle.ew_green_ms}")
            self._publish_car("N", "STOP")
            self._publish_car("S", "STOP")
        return True

    def _publish_car(self, direction: str, payload: str) -> None:
        topic = TOPIC_CARS[direction]
        result = self.client.publish(topic, payload, qos=1, retain=False)
        result.wait_for_publish()
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"[mqtt] Failed to publish car cmd ({topic} -> {payload})")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Road MQTT publisher")
    parser.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT broker host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT broker port")
    parser.add_argument("--client-id", default=None, help="MQTT client id")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    publisher = TrafficPublisher(host=args.broker, port=args.port, client_id=args.client_id)
    publisher.start()

    stop_requested = threading.Event()

    def _handle_stop(signum, frame):
        stop_requested.set()

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    last_order = "NS"
    try:
        for counts in count_stream():
            if stop_requested.is_set():
                break
            cycle = plan_cycle(counts["N"], counts["S"], counts["E"], counts["W"], last_order)
            if publisher.publish_cycle(cycle):
                last_order = cycle.order
    except KeyboardInterrupt:
        pass
    finally:
        publisher.stop()


if __name__ == "__main__":
    main()
