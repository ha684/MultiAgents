from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(app):
    # Đọc tên service từ biến môi trường đã set trong docker-compose
    # Điều này giúp bạn biết trace này đến từ service nào
    resource = Resource.create(attributes={"service.name": "kms-app"})

    # Khởi tạo TracerProvider
    provider = TracerProvider(resource=resource)
    # Cấu hình exporter để gửi trace đến Jaeger qua OTLP HTTP
    # Endpoint được đọc tự động từ biến môi trường OTEL_EXPORTER_OTLP_ENDPOINT
    exporter = OTLPSpanExporter()

    # Dùng BatchSpanProcessor để gửi trace theo lô, hiệu quả hơn
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    # Set provider này làm provider mặc định cho toàn ứng dụng
    trace.set_tracer_provider(provider)

    # Tự động instrument FastAPI.
    # Thao tác này sẽ tự động tạo span cha cho mỗi request đến.
    FastAPIInstrumentor.instrument_app(app)


# Lấy một tracer để sử dụng trong code của chúng ta
tracer = trace.get_tracer(__name__)
