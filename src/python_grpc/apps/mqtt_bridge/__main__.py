"""CLI entry point for running the MQTT-to-gRPC Ingestion Bridge."""

from python_grpc.apps.mqtt_bridge.app import main

if __name__ == "__main__":
    main()
