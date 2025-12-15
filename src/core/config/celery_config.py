# src/core/config/celery_config.py
import os

from src.core.config.settings import settings

# Broker configuration - prefer RabbitMQ if configured, fallback to Redis
# Check if RabbitMQ is configured
_rabbitmq_host = os.getenv("RABBITMQ_HOST", settings.rabbitmq_host)
_use_rabbitmq = _rabbitmq_host and _rabbitmq_host != "localhost"

if _use_rabbitmq:
    # Use RabbitMQ broker
    broker_url = settings.celery_broker_url
    result_backend = settings.celery_result_backend

    broker_transport_options = {
        "visibility_timeout": 3300,
    }

    result_backend_transport_options = {
        "connection_pool_kwargs": {"max_connections": 20, "retry_on_timeout": True},
    }
else:
    # Fallback to Redis broker
    broker_url = settings.redis_uri or settings.redis_url or "redis://localhost:6379/0"
    result_backend = (
        settings.redis_uri or settings.redis_url or "redis://localhost:6379/0"
    )

    broker_transport_options = {"master_name": "mymaster", "visibility_timeout": 3300}

    result_backend_transport_options = {
        "master_name": "mymaster",
        "connection_pool_kwargs": {"max_connections": 20, "retry_on_timeout": True},
    }

# Connection pool settings for better performance
broker_connection_retry_on_startup = True
broker_connection_max_retries = 10


# Serialization
task_serializer = "json"
accept_content = ["json"]
result_serializer = "json"
timezone = "UTC"
enable_utc = True

# Task execution settings
task_acks_late = True
task_reject_on_worker_lost = True
task_track_started = True

# Worker optimization for high throughput
worker_max_tasks_per_child = 100  # Reduced from 1000 for better memory management
worker_prefetch_multiplier = 4  # Increased from 1 for better throughput
worker_concurrency = 4  # Adjust based on your CPU cores

# Memory management
worker_max_memory_per_child = 200000  # 200MB per child (adjust based on file sizes)

# Task routing with priority queues
task_routes = {
    "tasks.process_document": {"queue": "document_processing"},
    "tasks.generate_and_stream": {"queue": "llm_streaming"},
}

# Queue configuration with different priorities
task_queue_ha_policy = "all"
task_default_queue = "document_processing"
task_default_exchange = "tasks"
task_default_exchange_type = "direct"
task_default_routing_key = "task"

# Define queues
task_queues = {
    "document_processing": {
        "exchange": "tasks",
        "routing_key": "document_processing",
    },
    "llm_streaming": {
        "exchange": "tasks",
        "routing_key": "llm_streaming",
    },
}

# Result handling
task_ignore_result = False
result_expires = 60 * 60 * 4  # Reduced from 24h to 4h to save memory
result_compression = "gzip"  # Compress results to save Redis memory

# Retry configuration
task_retry_backoff = True
task_retry_backoff_max = 700
task_retry_jitter = True
task_max_retries = 3

# Rate limiting
task_annotations = {
    "tasks.process_document": {
        "rate_limit": "100/m",  # 100 tasks per minute
        "time_limit": 1800,  # 30 minutes timeout
        "soft_time_limit": 1500,  # 25 minutes soft timeout
    },
    "tasks.generate_and_stream": {
        "rate_limit": "200/m",  # 200 streaming requests per minute
        "time_limit": 900,  # 15 minutes timeout
        "soft_time_limit": 600,  # 10 minutes soft timeout
    },
}

worker_send_task_events = True
task_send_sent_event = True
worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
worker_task_log_format = "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s"

# Imports
imports = ["src.tasks.file", "src.tasks.streaming"]

# Beat schedule for cleanup tasks (if using celery beat)
beat_schedule = {
    "cleanup-expired-results": {
        "task": "src.tasks.file.cleanup_temp_files",
        "schedule": 3600.0,  # Run every hour
    },
}

# Additional optimizations for file processing
task_compression = "gzip"
worker_disable_rate_limits = False
task_always_eager = False  # Make sure this is False in production

worker_heartbeat = 120
