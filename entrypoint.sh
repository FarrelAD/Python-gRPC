#!/bin/sh
set -e

# ==============================================================================
# Unified Container Entrypoint Script
# Dispatches execution based on service name or executes custom commands.
# ==============================================================================

show_help() {
    echo "Python gRPC & MQTT IoT Multi-Service Container"
    echo ""
    echo "Usage: docker run <image> [service_name|command] [args...]"
    echo ""
    echo "Available Services:"
    echo "  collector        Run central gRPC collector & embedded MQTT consumer"
    echo "  gateway          Run FastAPI REST-to-gRPC gateway"
    echo "  sensor-node      Run simulated MQTT sensor node (ESP32 PZEM-004T)"
    echo "  help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  docker run <image> collector --host 0.0.0.0 --port 50051"
    echo "  docker run <image> gateway --host 0.0.0.0 --port 8000"
    echo "  docker run <image> sensor-node --broker-host localhost --count 10"
    echo "  docker run <image> python -m pytest tests/"
}

case "$1" in
    collector)
        shift
        exec python -m python_grpc.apps.collector "$@"
        ;;
    gateway|rest-gateway)
        shift
        exec python -m python_grpc.apps.rest_gateway "$@"
        ;;
    sensor-node|mqtt-sensor-node)
        shift
        exec python -m python_grpc.apps.mqtt_sensor_node "$@"
        ;;
    help|--help|-h)
        show_help
        exit 0
        ;;
    "")
        echo "No command specified. Displaying usage:"
        show_help
        exit 1
        ;;
    *)
        # Allow passing arbitrary commands (e.g., bash, pytest, python, etc.)
        exec "$@"
        ;;
esac
