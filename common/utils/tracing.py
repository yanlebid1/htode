# common/utils/tracing.py
import os
import logging

logger = logging.getLogger(__name__)


def init_tracing(service_name: str):
    """Initialize OpenTelemetry tracing for a service.

    If the OpenTelemetry SDK is not installed or Jaeger is unreachable,
    tracing is silently disabled so the service continues to function.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        endpoint = os.getenv("OTEL_EXPORTER_ENDPOINT", "http://jaeger:4317")
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry tracing initialized for %s", service_name)
        return trace.get_tracer(service_name)
    except ImportError:
        logger.info("OpenTelemetry SDK not installed — tracing disabled")
        return None
    except Exception as e:
        logger.warning("Failed to initialize tracing: %s", e)
        return None
