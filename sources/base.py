from abc import ABC, abstractmethod
from typing import ClassVar

from sources.models import Media


class Source(ABC):
    """Uma fonte de dados. Cada fonte nova é uma subclasse que implementa `fetch`."""

    name: ClassVar[str]

    @abstractmethod
    def fetch(self, external_id: str, **kwargs: object) -> Media:
        """Filme (ou conteúdo por seu identificador principal)."""

    def fetch_serie(self, external_id: str, season: int | None = None, episode: int | None = None, **kwargs: object) -> Media:
        """Séries/temporadas/episódios quando a fonte suportar."""
        raise NotImplementedError(f"{type(self).__name__} não suporta séries")
