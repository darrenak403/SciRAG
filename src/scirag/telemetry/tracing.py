"""Traces of answered questions, sent to Phoenix when an endpoint is configured.

Attribute names follow the OpenInference conventions, which is what Phoenix
reads to show a span as a retrieval, a reranking or a model call.
"""

from functools import lru_cache

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer

from scirag.config import get_settings

SPAN_KIND = "openinference.span.kind"


@lru_cache
def get_tracer_provider() -> TracerProvider:
    provider = TracerProvider(
        resource=Resource.create({"service.name": "scirag", "openinference.project.name": "scirag"})
    )
    # Without an endpoint spans still get ids, so answers can record their trace id.
    if endpoint := get_settings().otlp_endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    return provider


def get_tracer() -> Tracer:
    return get_tracer_provider().get_tracer("scirag")
