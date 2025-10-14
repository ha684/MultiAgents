from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased


def setup_tracing(app, sampling_rate=1.0):
    """
    Setup OpenTelemetry tracing
    """
    resource = Resource.create(attributes={"service.name": "kms-app"})
    sampler = TraceIdRatioBased(sampling_rate)
    provider = TracerProvider(resource=resource, sampler=sampler)
    exporter = OTLPSpanExporter()
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


tracer = trace.get_tracer(__name__)
