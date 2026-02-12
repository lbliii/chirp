# Production Deployment

Guide to deploying chirp apps in production with pounce's enterprise features.

## Overview

Chirp apps run on [pounce](https://github.com/yourusername/pounce), a production-grade ASGI server with:

- **Phase 5 Features** (Automatic):
  - WebSocket compression (60% bandwidth reduction)
  - HTTP/2 support
  - Graceful shutdown and reload
  - Zero-copy static file serving
  - OpenTelemetry distributed tracing

- **Phase 6 Features** (Configurable):
  - Prometheus metrics endpoint
  - Per-IP rate limiting
  - Request queueing and load shedding
  - Sentry error tracking
  - Zero-downtime hot reload

## Quick Start

### Development Mode

```python
from chirp import App

app = App(config=AppConfig(debug=True))

@app.route("/")
def index():
    return "Hello!"

app.run()  # Development server
```

### Production Mode

```python
from chirp import App, AppConfig
from chirp.server.production import run_production_server

config = AppConfig(
    debug=False,
    secret_key="your-secret-key-here",
)

app = App(config=config)

@app.route("/")
def index():
    return "Hello!"

if __name__ == "__main__":
    run_production_server(
        app,
        workers=4,
        metrics_enabled=True,
        rate_limit_enabled=True,
    )
```

## Automatic Features (Phase 5)

These features work automatically with zero configuration:

### WebSocket Compression

**Enabled by default.** Reduces WebSocket bandwidth by ~60%.

```python
# No configuration needed - just works!
@app.sse("/events")
async def events():
    yield {"data": "Large payload compressed automatically"}
```

### HTTP/2 Support

**Works automatically with TLS.** Multiplexed streams, server push, better performance.

```bash
# Generate TLS certificate
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes

# Run with TLS (enables HTTP/2)
python production.py --ssl-certfile cert.pem --ssl-keyfile key.pem
```

### Graceful Shutdown

**Handles SIGTERM gracefully.** Finishes active requests before shutting down.

```bash
# Kubernetes sends SIGTERM before SIGKILL
kill -TERM <pid>  # Gracefully completes in-flight requests
```

### Zero-Downtime Reload

**Hot reload without dropping connections.** Perfect for deployments.

```bash
# Send SIGUSR1 to supervisor process
kill -SIGUSR1 <pid>

# New workers start, old workers drain, zero dropped connections
```

### OpenTelemetry (Distributed Tracing)

**Enable with configuration:**

```python
run_production_server(
    app,
    otel_endpoint="http://localhost:4318",  # OTLP endpoint
    otel_service_name="my-chirp-app",
)
```

Automatic traces for all HTTP requests with duration, status, and span propagation.

## Production Features (Phase 6)

Enable these features via configuration for production-grade protection:

### Prometheus Metrics

**Monitor your app with industry-standard metrics:**

```python
run_production_server(
    app,
    metrics_enabled=True,      # Enable /metrics endpoint
    metrics_path="/metrics",   # Customize path (optional)
)
```

**Access metrics:**
```bash
curl http://localhost:8000/metrics
```

**Metrics exposed:**
- `http_requests_total` - Total requests by method/status
- `http_request_duration_seconds` - Request latency histogram
- `http_connections_active` - Current active connections
- `http_requests_in_flight` - Currently processing requests
- `http_bytes_sent_total` - Total bytes sent

**Integrate with Prometheus:**

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'chirp-app'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Rate Limiting

**Protect against abusive clients:**

```python
run_production_server(
    app,
    rate_limit_enabled=True,
    rate_limit_requests_per_second=100.0,  # 100 req/s per IP
    rate_limit_burst=200,                   # Allow bursts up to 200
)
```

**How it works:**
- Each client IP gets its own token bucket
- Tokens refill at configured rate
- Burst allows temporary spikes
- Rate limited clients get `429 Too Many Requests`

**Choosing limits:**
- **Conservative (public APIs):** 10-50 req/s, burst 2-5x
- **Moderate (web apps):** 50-100 req/s, burst 2x
- **Lenient (internal):** 100-1000 req/s, burst 5-10x

### Request Queueing

**Handle traffic spikes gracefully:**

```python
run_production_server(
    app,
    request_queue_enabled=True,
    request_queue_max_depth=1000,  # Queue up to 1000 requests
)
```

**How it works:**
- Buffers requests when workers are busy
- Returns `503 Service Unavailable` when queue is full
- Prevents server overload and resource exhaustion

**Choose queue depth:**
```
queue_depth ≈ peak_rps × acceptable_wait_seconds
```

Example: 1000 req/s peak, 2s acceptable wait = 2000 queue depth

### Sentry Error Tracking

**Automatic error reporting:**

```python
run_production_server(
    app,
    sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
    sentry_environment="production",
    sentry_release="myapp@1.0.0",
)
```

**What's captured:**
- All uncaught exceptions
- Full request context (headers, method, path, etc.)
- User information (if available)
- Stack traces with source code

**Requirements:**
```bash
pip install sentry-sdk
```

## Complete Production Configuration

```python
from chirp import App, AppConfig
from chirp.server.production import run_production_server
import os

# Application config
config = AppConfig(
    debug=False,
    secret_key=os.getenv("SECRET_KEY"),
    host="0.0.0.0",
    port=8000,
)

app = App(config=config)

# Your routes here...

if __name__ == "__main__":
    run_production_server(
        app,
        host="0.0.0.0",
        port=8000,
        workers=4,  # Multi-worker for zero-downtime reload

        # Observability
        metrics_enabled=True,
        lifecycle_logging=True,
        log_format="json",

        # Protection
        rate_limit_enabled=True,
        rate_limit_requests_per_second=100.0,
        rate_limit_burst=200,

        # Overload handling
        request_queue_enabled=True,
        request_queue_max_depth=1000,

        # Error tracking
        sentry_dsn=os.getenv("SENTRY_DSN"),
        sentry_environment="production",
        sentry_release="myapp@1.0.0",

        # Distributed tracing
        otel_endpoint=os.getenv("OTEL_ENDPOINT"),

        # Hot reload
        reload_timeout=60.0,
    )
```

## Kubernetes Deployment

### Basic Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chirp-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: chirp-app
  template:
    metadata:
      labels:
        app: chirp-app
    spec:
      containers:
      - name: app
        image: myapp:latest
        ports:
        - containerPort: 8000
        env:
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: chirp-secrets
              key: secret-key
        - name: SENTRY_DSN
          valueFrom:
            secretKeyRef:
              name: chirp-secrets
              key: sentry-dsn
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: chirp-app
spec:
  selector:
    app: chirp-app
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

### Rolling Updates (Zero-Downtime)

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # Zero downtime
  template:
    spec:
      containers:
      - name: app
        lifecycle:
          preStop:
            exec:
              # Send SIGUSR1 for graceful reload
              command: ["sh", "-c", "kill -SIGUSR1 1 && sleep 30"]
        terminationGracePeriodSeconds: 60
```

### ConfigMap for Configuration

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: chirp-config
data:
  WORKERS: "4"
  METRICS_ENABLED: "true"
  RATE_LIMIT_ENABLED: "true"
  RATE_LIMIT_RPS: "100"
  QUEUE_ENABLED: "true"
  QUEUE_MAX_DEPTH: "1000"
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: app
        envFrom:
        - configMapRef:
            name: chirp-config
```

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run production server
CMD ["python", "production.py"]

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
```

### Docker Compose

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - SENTRY_DSN=${SENTRY_DSN}
      - WORKERS=4
      - METRICS_ENABLED=true
      - RATE_LIMIT_ENABLED=true
    restart: unless-stopped

  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-storage:/var/lib/grafana

volumes:
  grafana-storage:
```

## Environment Variables

Recommended environment-based configuration:

```bash
# .env.production
SECRET_KEY=your-secret-key-here
DEBUG=false

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4

# Observability
METRICS_ENABLED=true
LIFECYCLE_LOGGING=true
LOG_FORMAT=json

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_RPS=100
RATE_LIMIT_BURST=200

# Request Queue
QUEUE_ENABLED=true
QUEUE_MAX_DEPTH=1000

# Sentry
SENTRY_DSN=https://...
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=myapp@1.0.0

# OpenTelemetry
OTEL_ENDPOINT=http://localhost:4318
```

## Performance Tuning

### Worker Count

```python
import os

# Auto-detect from CPU count
workers = int(os.getenv("WORKERS", 0))  # 0 = auto

# Or explicit count
workers = 4  # Good for 2-4 CPU cores
```

**Guidelines:**
- CPU-bound: `workers = cpu_count`
- I/O-bound: `workers = 2-4 × cpu_count`
- Start with auto-detect, tune based on metrics

### Connection Limits

```python
ServerConfig(
    max_connections=1000,       # Global connection limit
    backlog=2048,               # TCP backlog
    keep_alive_timeout=5.0,     # Keep-alive duration
    request_timeout=30.0,       # Request timeout
)
```

### Timeouts

```python
run_production_server(
    app,
    reload_timeout=60.0,        # Worker drain timeout
    request_timeout=30.0,       # Individual request timeout
)
```

## Monitoring

### Prometheus + Grafana

1. **Start Prometheus:**
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'chirp'
    static_configs:
      - targets: ['app:8000']
    metrics_path: '/metrics'
```

2. **Query metrics:**
```promql
# Request rate
rate(http_requests_total[5m])

# P95 latency
histogram_quantile(0.95, http_request_duration_seconds_bucket)

# Error rate
rate(http_requests_total{status=~"5.."}[5m])
```

3. **Create Grafana dashboard** with these panels:
- Request rate (RPS)
- P50/P95/P99 latency
- Error rate (%)
- Active connections

## Security Checklist

- [ ] Set `debug=False` in production
- [ ] Use strong `secret_key` (generate with `secrets.token_urlsafe()`)
- [ ] Enable TLS with valid certificates
- [ ] Enable rate limiting
- [ ] Set appropriate CORS policies
- [ ] Use environment variables for secrets
- [ ] Enable Sentry error tracking
- [ ] Monitor metrics for anomalies
- [ ] Set up health checks
- [ ] Configure graceful shutdown timeouts

## Troubleshooting

### High CPU Usage

Check:
- Worker count (too many workers)
- Request rate (need rate limiting)
- Slow endpoints (optimize code)

### High Memory Usage

Check:
- Queue depth (lower max_depth)
- Connection leaks (check lifecycle hooks)
- Large request bodies (set limits)

### Connection Drops During Deploy

Enable:
- Zero-downtime reload (`kill -SIGUSR1`)
- Kubernetes rolling updates with `maxUnavailable: 0`
- Grace period in container config

### Rate Limiting Too Aggressive

Increase:
- `rate_limit_requests_per_second`
- `rate_limit_burst`

Or disable for internal services.

## Next Steps

- Set up CI/CD pipeline
- Configure monitoring and alerts
- Load test your application
- Set up backups and disaster recovery
- Document runbooks for operations

---

**See Also:**
- [Pounce Documentation](https://github.com/yourusername/pounce)
- [Prometheus Metrics](https://github.com/yourusername/pounce/docs/deployment/prometheus-metrics.md)
- [Rate Limiting](https://github.com/yourusername/pounce/docs/deployment/rate-limiting.md)
