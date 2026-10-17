import unittest
from typing import ClassVar

from sources.base import Source
from sources.models import Media, MediaKind, StreamLink
from sources.registry import SourceRegistry


class FakeSource(Source):
    name: ClassVar[str] = "fake"

    def fetch(self, external_id: str, **kwargs: object) -> Media:
        return Media(
            external_id=external_id,
            title="Título de teste",
            kind=MediaKind.MOVIE,
            links=[StreamLink(url="https://exemplo.invalid/video.mp4", resolution="720p")],
        )


class SourceRegistryTest(unittest.TestCase):
    def test_extract_usa_fonte_registrada(self) -> None:
        registry = SourceRegistry()
        registry.register(FakeSource())

        media = registry.extract("fake", "tt0000001")

        self.assertEqual(media.external_id, "tt0000001")
        self.assertEqual(media.kind, MediaKind.MOVIE)
        self.assertEqual(media.links[0].resolution, "720p")

    def test_nome_duplicado_levanta_erro(self) -> None:
        registry = SourceRegistry()
        registry.register(FakeSource())

        with self.assertRaises(ValueError):
            registry.register(FakeSource())

    def test_fonte_desconhecida_levanta_erro(self) -> None:
        registry = SourceRegistry()

        with self.assertRaises(KeyError):
            _ = registry.extract("nao_existe", "tt0000001")

    def test_names_lista_fontes_em_ordem(self) -> None:
        registry = SourceRegistry()
        registry.register(FakeSource())

        self.assertEqual(registry.names(), ["fake"])


if __name__ == "__main__":
    _ = unittest.main()
