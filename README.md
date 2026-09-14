# Python gRPC — PZEM-004t Industry-Grade Microservices & Gateway Prototype

An end-to-end demonstration of **industry-grade gRPC in Python** using the async
`grpc.aio` API. A simulated electrical device reads live data from a
**PZEM-004t** AC power meter (voltage, current, active power, energy,
frequency, power factor) and pushes it over gRPC to a collector server, with an
optional **FastAPI REST-to-gRPC Gateway** allowing external REST API consumers to
interact with the gRPC microservice.

## Architecture

```mermaid
flowchart LR
    subgraph Microcontrollers["IoT Microcontrollers (e.g. ESP32)"]
        ESP32["ESP32 + PZEM-004T\n(apps/mqtt_sensor_node)\n[paho-mqtt]"]
    end

    subgraph MQTTBroker["MQTT Messaging Broker (Port 1883)"]
        Broker["Eclipse Mosquitto\n(devices/+/telemetry)"]
    end

    subgraph Collector["Telemetry Collector Service (Port 50051)"]
        MQTTSub["Embedded MQTT Consumer\n(paho-mqtt)"]
        Serv["DeviceTelemetryServicer\n(Pub/Sub & In-Memory Store)"]
        gRPCServer["gRPC Server (HTTP/2)\n(Port 50051)"]
        MQTTSub -->|"Internal Ingest"| Serv
        Serv <--> gRPCServer
    end

    subgraph RESTConsumer["Web / Mobile / Dashboard"]
        REST["REST-to-gRPC Gateway\n(apps/rest_gateway)\n(FastAPI - Port 8000)"]
    end

    ESP32 -->|"MQTT Publish (JSON)"| Broker
    Broker -->|"MQTT Subscribe"| MQTTSub
    REST ==>|"gRPC Unary & Batch (HTTP/2)"| gRPCServer
```

### Industry-Grade Capabilities Implemented

- **Industrial IoT Protocol Hierarchy**:
  - **MQTT**: Lightweight pub/sub for resource-constrained microcontrollers (ESP32) reading PZEM-004T sensors.
  - **Embedded MQTT Ingestion**: Telemetry Collector directly consumes MQTT telemetry topics into its real-time pub/sub hub.
  - **FastAPI REST Gateway**: Modular HTTP backend for external web/mobile dashboards and REST API consumers.
- **gRPC Interceptors**:
  - **Client-Side**: Injects distributed tracing headers (`x-request-id`) and `x-client-version`.
  - **Server-Side**: Performance metrics logging (RPC duration, peer IP, status code) and unhandled exception recovery translating errors safely into gRPC status codes.
- **Official Health Checking (`grpc.health.v1`)**: Exposes standard gRPC health checks for Kubernetes liveness/readiness probes and load balancers.
- **Connection Resilience**: Configured HTTP/2 keepalive pings (`grpc.keepalive_time_ms`), request timeouts (deadlines), and auto-reconnects.
- **Container Orchestration**: Multi-container Docker Compose topology orchestrating Mosquitto MQTT, Collector (with embedded MQTT subscriber), and REST Gateway across segmented bridge networks.

### The four gRPC call types

| RPC | Type | Direction | Meaning |
|---|---|---|---|
| `ReportReading` | unary-unary | client → server | device reports one reading, gets an `Ack` |
| `ReportReadings` | client-streaming | client ⇉ server | batch upload, server replies with a `BatchSummary` |
| `Subscribe` | server-streaming | server ⇉ client | collector streams live readings for a device |
| `StreamTelemetry` | bidi-streaming | client ⇄ server | continuous two-way exchange, ack per reading |

### File layout

```
src/python_grpc/
  proto/                       # protobuf schema + generated stubs
    pzem_004t.proto            # schema (authoritative)
    pzem_004t_pb2.py           # generated message classes
    pzem_004t_pb2_grpc.py      # generated service stubs
  core/                        # shared core domain and infrastructure
    common/
      config.py                # HTTP/2 keepalive & channel options
      interceptors.py          # client & server interceptors (tracing, metrics)
    device/
      pzem_004t.py             # PZEM004TDevice hardware physics simulator
  apps/                        # autonomous deployable applications
    collector/                 # Cloud-tier: Telemetry Collector Server (gRPC + Embedded MQTT)
      app.py                   # server lifecycle, embedded MQTT consumer, health check
      mqtt_consumer.py         # paho-mqtt background subscriber feeding servicer directly
      servicer.py              # in-memory pub/sub telemetry broadcast servicer
      __main__.py              # CLI entry point (python -m python_grpc.apps.collector)
    mqtt_sensor_node/          # Edge-tier: Microcontroller (ESP32) MQTT Sensor Node
      app.py                   # sensor reading & MQTT JSON publishing loop
      __main__.py              # CLI entry point (python -m python_grpc.apps.mqtt_sensor_node)
    rest_gateway/              # Consumer-tier: Modular FastAPI REST-to-gRPC Gateway
      app.py                   # FastAPI app factory & lifespan
      config.py                # Gateway configuration settings
      dependencies.py          # Dependency injection & stub resolver
      schemas.py               # Pydantic models for validation
      routers/                 # Modular APIRouters (telemetry, health)
      __main__.py              # CLI entry point (python -m python_grpc.apps.rest_gateway)
scripts/
  gen_proto.py                 # regenerate stubs from the proto
  simulate_cross_host.py       # multi-host cross-network simulation script
tests/
  test_device.py               # sensor simulator unit tests
  test_telemetry.py            # end-to-end 4 gRPC streaming patterns
  test_cross_host.py           # multi-client pub/sub broadcasting & disconnect resilience
  test_health_and_interceptors.py # gRPC health & interceptor integration tests
  test_gateway.py              # FastAPI REST-to-gRPC gateway integration tests
  test_mqtt_pipeline.py        # Embedded MQTT ingestion & gRPC live streaming tests
Dockerfile                     # multi-app container build
docker-compose.yml             # multi-network orchestration with Mosquitto MQTT broker
```

## Requirements

- Python >= 3.13
- [Poetry](https://python-poetry.org/) (project is Poetry-managed)
- Docker & Docker Compose (optional, for containerized run)

## Setup

```bash
poetry install
```

## Running the Applications

### Option A: Running via Poetry locally

#### 1. Start the Telemetry Collector Server (Terminal 1)
```bash
poetry run python -m python_grpc.apps.collector --host 0.0.0.0 --port 50051 --mqtt-host localhost --mqtt-port 1883
```

#### 2. Start the REST-to-gRPC Gateway (Terminal 2)
```bash
poetry run python -m python_grpc.apps.rest_gateway --host 0.0.0.0 --port 8000 --grpc-target localhost:50051
```
Open your browser at `http://localhost:8000/docs` to test Swagger UI or send a cURL request:
```bash
curl -X POST "http://localhost:8000/api/telemetry" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "REST-01", "voltage": 230.2, "current": 2.1, "active_power": 483.4, "energy": 1.2, "frequency": 50.0, "power_factor": 0.99}'
```

#### 3. Run the Simulated ESP32 Sensor Node (Terminal 3)
If you have an MQTT broker running (such as Mosquitto on port 1883):
```bash
# Start Simulated ESP32 reading PZEM-004T and publishing over MQTT
poetry run python -m python_grpc.apps.mqtt_sensor_node --broker-host localhost --broker-port 1883 --device-id ESP32-PZEM-01 --count 5
```

### Option B: Running with Docker Compose
Spin up the entire microservice topology (Mosquitto MQTT broker, Collector with embedded MQTT, and REST Gateway):
```bash
docker compose up --build
```

## Running Tests

```bash
poetry run pytest -v --cov=python_grpc
```

Tests run 18 automated integration and unit tests covering:
- Sensor physics and energy accumulation ([`tests/test_device.py`](tests/test_device.py))
- All 4 gRPC streaming patterns ([`tests/test_telemetry.py`](tests/test_telemetry.py))
- Cross-host multi-client pub/sub broadcasting & disconnect resilience ([`tests/test_cross_host.py`](tests/test_cross_host.py))
- Standard gRPC Health Checking (`grpc.health.v1`) & Interceptors ([`tests/test_health_and_interceptors.py`](tests/test_health_and_interceptors.py))
- FastAPI REST-to-gRPC unary and batch forwarding ([`tests/test_gateway.py`](tests/test_gateway.py))
- Simulated ESP32 MQTT pub/sub ingestion into gRPC Collector ([`tests/test_mqtt_pipeline.py`](tests/test_mqtt_pipeline.py))

## Code Formatting & Linting

Ruff is used for ultra-fast linting and code formatting:
```bash
# Check for lint violations
poetry run ruff check .

# Automatically apply safe lint fixes
poetry run ruff check --fix .

# Check formatting without modifying files
poetry run ruff format --check .

# Automatically format the entire codebase
poetry run ruff format .
```

## Type Checking

Pyrefly runs in `strict` mode against the entire codebase (`preset = "strict"` in `pyproject.toml`):
```bash
poetry run pyrefly check
```

## CI/CD Deployment with GitHub Actions

The repository includes preconfigured GitHub Actions workflows in `.github/workflows/`:

1. **Continuous Integration (`.github/workflows/ci.yml`)**:
   - Triggers on PRs and pushes to `main`.
   - Runs Python 3.13 with Poetry dependency caching.
   - Verifies Protobuf stub freshness (fails if generated code drifted from `pzem_004t.proto`).
   - Runs strict Pyrefly type checking.
   - Executes all 14 integration and unit tests.

2. **Manual Deployment to Target Server (`.github/workflows/deploy.yml`)**:
   - Strictly developer-triggered via GitHub Actions **"Run workflow"** (`workflow_dispatch`).
   - Supports parameter selection:
     - `environment`: `staging` or `production`.
     - `run_tests`: Boolean toggle to run or skip full test verification before deploy.
     - `deploy_tag`: Optional specific image tag or commit SHA.
   - **Job 1 (verify-tests)**: Runs strict type checks and the 14 automated tests (conditional).
   - **Job 2 (build-and-push)**: Builds multi-architecture images (`linux/amd64`, `linux/arm64`) and pushes to **GHCR** (`ghcr.io/farrelad/python-grpc`).
   - **Job 3 (deploy-remote)**: Connects via SSH to the remote host, pulls pre-built images with `IMAGE_NAME=ghcr.io/farrelad/python-grpc docker compose pull`, performs a zero-downtime container recreation with `docker compose up -d`, and verifies service health with a live HTTP `/health` probe.

### Target Server GitHub Secrets
To deploy to a remote server, configure these in **Settings -> Secrets and variables -> Actions**:
- `SERVER_HOST`: Remote server IP address or hostname
- `SERVER_USER`: Remote SSH username (e.g. `ubuntu`)
- `SERVER_SSH_KEY`: Private SSH key authorized on the server
- `SERVER_DEPLOY_PATH`: Target directory on the server containing `docker-compose.yml` (default: `/opt/python-grpc`)
- `SERVER_PORT`: (Optional) SSH port, defaults to 22
