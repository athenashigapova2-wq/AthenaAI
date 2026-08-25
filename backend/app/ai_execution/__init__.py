"""Canonical execution boundary for every provider-backed AI operation."""

from app.ai_execution.gateway import AIExecutionLayer, ai_execution_layer

__all__ = ["AIExecutionLayer", "ai_execution_layer"]
