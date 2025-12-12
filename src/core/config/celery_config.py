# src/core/config/celery_config.py
from src.core.config.settings import settings

# Redis connection settings
broker_url = settings.redis_url
result_backend = settings.redis_url

broker_transport_options = {"master_name": "mymaster", "visibility_timeout": 3300}

# Connection pool settings for better Redis performance
broker_connection_retry_on_startup = True
broker_connection_max_retries = 10

result_backend_transport_options = {
    "master_name": "mymaster",
    "connection_pool_kwargs": {"max_connections": 20, "retry_on_timeout": True},
}


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
}

# Queue configuration with different priorities
task_queue_ha_policy = "all"
task_default_queue = "document_processing"
task_default_exchange = "tasks"
task_default_exchange_type = "direct"
task_default_routing_key = "task"

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
}

worker_send_task_events = True
task_send_sent_event = True
worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
worker_task_log_format = "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s"

# Imports
imports = ["src.tasks.file"]

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
