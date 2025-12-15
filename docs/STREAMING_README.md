# Kafka-Backed LLM Streaming with Resume

This document describes the architecture and usage of the Kafka-backed LLM streaming pipeline with resume capability.

## Overview

The streaming pipeline enables ChatGPT-like behavior where:
- Clients can disconnect and reconnect without losing tokens
- Tokens are durably stored in Kafka for replay
- Multiple delivery mechanisms (SSE and WebSocket)
- Automatic cleanup via Kafka retention

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│   FastAPI    │────▶│   Celery    │
│  (Browser)  │     │   Gateway    │     │   Worker    │
└─────────────┘     └──────────────┘     └─────────────┘
       │                   │                    │
       │                   │                    ▼
       │                   │            ┌─────────────┐
       │                   │            │    vLLM     │
       │                   │            │   Server    │
       │                   │            └─────────────┘
       │                   │                    │
       │                   ▼                    ▼
       │            ┌─────────────────────────────────┐
       │            │           Kafka                 │
       │            │    Topic: llm.responses         │
       │            │    (partitioned by request_id)  │
       │            └─────────────────────────────────┘
       │                          │
       ▼                          ▼
┌─────────────┐           ┌─────────────┐
│  SSE/WS     │◀──────────│   Kafka     │
│  Stream     │           │  Consumer   │
└─────────────┘           └─────────────┘
```

## Quick Start

### 1. Start Infrastructure

```bash
cd docker
docker-compose up -d kafka rabbitmq redis postgres
```

Wait for services to be healthy, then create topics:

```bash
docker-compose up kafka-init
```

### 2. Start the API Server

```bash
# From project root
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Start the Streaming Worker

```bash
# In another terminal
python -m src.streaming_worker
```

Or for the document processing worker:

```bash
python -m src.worker
```

## API Endpoints

### Start a Generation Request

```http
POST /v1/chat/completions
Content-Type: application/json
Authorization: Bearer <token>

{
  "messages": [
    {"role": "user", "content": "Hello, how are you?"}
  ],
  "conversation_id": "uuid",
  "kb_id": "uuid",
  "model": "nxchat-internal",
  "temperature": 0.7,
  "agentic": false,
  "web_search": false,
  "use_rag": true
}
```

Response:
```json
{
  "request_id": "abc123...",
  "status": "queued",
  "message": "Generation request queued successfully"
}
```

### Stream via SSE

```http
GET /v1/chat/stream/{request_id}
Accept: text/event-stream
Authorization: Bearer <token>
```

To resume from a previous position:
```http
GET /v1/chat/stream/{request_id}
Accept: text/event-stream
Authorization: Bearer <token>
Last-Event-ID: 0:42
```

SSE Event Format:
```
id: 0:42
event: delta
data: {"request_id": "...", "type": "delta", "delta": "Hello", "seq": 1}

id: 0:43
event: delta
data: {"request_id": "...", "type": "delta", "delta": " world", "seq": 2}

id: 0:44
event: done
data: {"request_id": "...", "type": "done", "finish_reason": "stop"}
```

### Stream via WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/v1/chat/ws');

ws.onopen = () => {
  // Send initial message with request_id
  ws.send(JSON.stringify({
    request_id: 'abc123...',
    cursor: null  // or '0:42' to resume
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(msg.type, msg.data, msg.cursor);
  
  // Store cursor for potential reconnect
  localStorage.setItem('last_cursor', msg.cursor);
};

// On disconnect, reconnect with last cursor
ws.onclose = () => {
  const cursor = localStorage.getItem('last_cursor');
  // Reconnect with cursor...
};
```

### Get Stream Status

```http
GET /v1/chat/status/{request_id}
Authorization: Bearer <token>
```

Response:
```json
{
  "request_id": "abc123...",
  "status": "running",
  "cursor": "0:42",
  "created_at": "2024-01-01T00:00:00Z"
}
```

## Resume/Reconnect Flow

### SSE Resume

1. Client receives events with `id` field (cursor)
2. Client stores last received `id`
3. On disconnect, client reconnects with `Last-Event-ID` header
4. Server replays events starting after that cursor

```javascript
const eventSource = new EventSource('/v1/chat/stream/abc123', {
  headers: {
    'Authorization': 'Bearer <token>',
    'Last-Event-ID': localStorage.getItem('lastEventId')
  }
});

eventSource.onmessage = (event) => {
  localStorage.setItem('lastEventId', event.lastEventId);
  // Process event...
};
```

### WebSocket Resume

1. Client receives messages with `cursor` field
2. Client stores last received `cursor`
3. On disconnect, client reconnects and sends initial message with `cursor`
4. Server replays events starting after that cursor

## Message Types

| Type | Description | Terminal |
|------|-------------|----------|
| `delta` | Partial token text | No |
| `meta` | Metadata (model, tokens, etc.) | No |
| `done` | Generation complete | Yes |
| `error` | Error occurred | Yes |

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses | `localhost:9092` |
| `KAFKA_TOPIC_LLM_RESPONSES` | Topic for LLM events | `llm.responses` |
| `KAFKA_TOPIC_PARTITIONS` | Number of partitions | `6` |
| `KAFKA_SECURITY_PROTOCOL` | Security protocol | `PLAINTEXT` |
| `KAFKA_RETENTION_HOURS` | Message retention | `24` |
| `RABBITMQ_HOST` | RabbitMQ host | `localhost` |
| `RABBITMQ_PORT` | RabbitMQ port | `5672` |
| `RABBITMQ_USER` | RabbitMQ username | `guest` |
| `RABBITMQ_PASSWORD` | RabbitMQ password | `guest` |
| `VLLM_BASE_URL` | vLLM server URL | `` |
| `VLLM_API_KEY` | vLLM API key | `` |
| `VLLM_MODEL` | Default model name | `` |

## Testing Resume Capability

### Test SSE Resume

1. Start a generation:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Write a long story about..."}]}'
```

2. Connect to SSE and receive some events:
```bash
curl -N http://localhost:8000/v1/chat/stream/<request_id> \
  -H "Authorization: Bearer <token>"
```

3. Kill the connection (Ctrl+C) after receiving some events. Note the last `id`.

4. Reconnect with `Last-Event-ID`:
```bash
curl -N http://localhost:8000/v1/chat/stream/<request_id> \
  -H "Authorization: Bearer <token>" \
  -H "Last-Event-ID: 0:42"
```

5. Verify you receive remaining events without duplicates.

### Test WebSocket Resume

Use the example JavaScript code in the WebSocket section, ensuring you store and send the cursor on reconnect.

## Kafka Topic Details

- **Topic Name**: `llm.responses`
- **Partitions**: 6 (configurable)
- **Retention**: 24 hours (configurable)
- **Partitioning Key**: `request_id` (ensures ordering per request)
- **Replication Factor**: 1 (increase for production)

## Monitoring

### Kafka UI

Access at http://localhost:8090 (when using docker-compose)

View:
- Topic messages
- Consumer lag
- Partition distribution

### Health Checks

```bash
# Check Kafka
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

# Check RabbitMQ
curl http://localhost:15672/api/health/checks/alarms
```

## Troubleshooting

### Stream not starting

1. Check Celery worker is running: `celery -A src.core.config.celery_app inspect ping`
2. Check RabbitMQ connection: `docker logs rabbitmq`
3. Check task was queued: `celery -A src.core.config.celery_app inspect active`

### Resume not working

1. Check Kafka retention hasn't expired
2. Verify cursor format is correct (`partition:offset`)
3. Check stream index store has the request_id

### Missing tokens

1. Check for Kafka consumer errors in logs
2. Verify partition assignment
3. Check for network issues between services

## Production Considerations

1. **Kafka Replication**: Increase replication factor to 3
2. **Security**: Enable SASL/SSL for Kafka
3. **Persistence**: Use Redis cluster for stream index store
4. **Monitoring**: Add Prometheus metrics for consumer lag
5. **Scaling**: Run multiple streaming workers and FastAPI instances

