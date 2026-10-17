"""Factory do registry padrão do projeto."""

from sources.myembed import MyEmbedSource
from sources.registry import SourceRegistry


def default_registry() -> SourceRegistry:
    registry = SourceRegistry()
    registry.register(MyEmbedSource())
    return registry
