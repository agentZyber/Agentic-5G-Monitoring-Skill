"""Declarative telecom/agentic dataset registry."""

from zortenet.datasets.registry import (
    Dataset,
    REGISTRY,
    datasets_for_role,
    get_dataset,
    list_datasets,
)

__all__ = ["Dataset", "REGISTRY", "datasets_for_role", "get_dataset", "list_datasets"]
