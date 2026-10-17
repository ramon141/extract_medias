from sources.base import Source
from sources.models import Media


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}

    def register(self, source: Source) -> None:
        if source.name in self._sources:
            raise ValueError(f"Fonte já registrada: {source.name}")
        self._sources[source.name] = source

    def names(self) -> list[str]:
        return sorted(self._sources)

    def extract(self, source_name: str, external_id: str, **kwargs: object) -> Media:
        source = self._fonte(source_name)
        return source.fetch(external_id, **kwargs)

    def extract_serie(
        self,
        source_name: str,
        external_id: str,
        season: int | None = None,
        episode: int | None = None,
    ) -> Media:
        source = self._fonte(source_name)
        return source.fetch_serie(external_id, season=season, episode=episode)

    def _fonte(self, source_name: str) -> Source:
        source = self._sources.get(source_name)
        if source is None:
            raise KeyError(f"Fonte desconhecida: {source_name}")
        return source
