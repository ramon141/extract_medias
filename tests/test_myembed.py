import unittest
from dataclasses import dataclass, field
from typing import ClassVar

from sources.base import Source
from sources.errors import SourceError
from sources.models import MediaKind, Season
from sources.myembed import MyEmbedSource
from sources.playerflix import PlayerFlixClient, ServerOption, TitleInfo
from sources.resolver import PlaywrightServerResolver, ServerResult
from sources.registry import SourceRegistry

OPTS_FILME = [
    ServerOption(id="watchplay", label="WatchPlay", embed_url="https://v1.watchplay.shop/movie/tt1"),
    ServerOption(id="embedplayer", label="VIP Player", embed_url="https://embedplayer2.xyz/video/x"),
]
INFO_FILME = TitleInfo(title="Homem-Aranha: Um Novo Dia", title_en="Spider-Man", poster="p.jpg")
OPTS_SERIE = [
    ServerOption(id="blogger", label="Blogger", embed_url="https://b/video.g?token=x"),
]


class ClienteFake(PlayerFlixClient):
    """PlayerFlixClient sem rede: respostas pré-programadas."""

    def __init__(
        self,
        filme: tuple[TitleInfo, list[ServerOption]] | None = None,
        episodio: tuple[TitleInfo, list[ServerOption]] | None = None,
    ) -> None:
        super().__init__()
        self.filme_resposta = filme or (TitleInfo(title="default"), [])
        self.episodio_resposta = episodio or (TitleInfo(title="serie"), [])
        self.ultimo_chamado: str = ""

    def filme(self, imdb_id: str) -> tuple[TitleInfo, list[ServerOption]]:
        self.ultimo_chamado = imdb_id
        return self.filme_resposta

    def temporada_episodio(
        self, tmdb_id: str, temporada: int | None, episodio: int | None
    ) -> tuple[TitleInfo, list[ServerOption]]:
        self.ultimo_chamado = tmdb_id
        return self.episodio_resposta

    def catalogo(self, tmdb_id: str) -> tuple[TitleInfo, dict[int, Season]]:
        self.ultimo_chamado = tmdb_id
        return TitleInfo(title="serie"), {}


@dataclass
class ResolverFake(PlaywrightServerResolver):
    """Resolver sem Playwright: streams programados por id de server."""

    mapa: dict[str, list[str]] = field(default_factory=dict[str, list[str]])

    def resolve(self, options: list[ServerOption], referer: str = "") -> list[ServerResult]:
        self.referer_recebido = referer
        return [
            ServerResult(option=option, streams=list(self.mapa.get(option.id, [])))
            for option in options
        ]


class FilmeTest(unittest.TestCase):
    def test_resolve_servers_para_streams(self) -> None:
        cliente = ClienteFake(filme=(INFO_FILME, list(OPTS_FILME)))
        resolver = ResolverFake(mapa={"watchplay": ["https://cdn/1080p.m3u8"]})
        fonte = MyEmbedSource(client=cliente, resolver=resolver)

        media = fonte.fetch("tt22084616")

        self.assertEqual(media.kind, MediaKind.MOVIE)
        self.assertEqual(media.title, "Homem-Aranha: Um Novo Dia")
        self.assertEqual(len(media.links), 1)
        link = media.links[0]
        self.assertEqual(link.url, "https://cdn/1080p.m3u8")
        self.assertEqual(link.resolution, "1080p")
        self.assertEqual(link.label, "WatchPlay")
        self.assertEqual(resolver.referer_recebido, "https://playerflix.ink/filme/tt22084616")

    def test_sem_stream_devolve_nada(self) -> None:
        cliente = ClienteFake(filme=(INFO_FILME, list(OPTS_FILME)))
        fonte = MyEmbedSource(client=cliente, resolver=ResolverFake())

        media = fonte.fetch("tt22084616")

        self.assertEqual(media.links, [])

    def test_server_indisponivel_e_pulado(self) -> None:
        indisponivel = ServerOption(id="premium", label="Premium", embed_url="https://p/x", healthy=False)
        cliente = ClienteFake(filme=(INFO_FILME, [indisponivel]))
        resolver = ResolverFake(mapa={"premium": ["https://cdn/x.m3u8"]})
        fonte = MyEmbedSource(client=cliente, resolver=resolver)

        media = fonte.fetch("tt22084616")

        self.assertEqual(media.links, [])

    def test_playerflix_desconhece_titulo_ainda_tenta_vidsrc(self) -> None:
        class ClienteQueNaoConhece(ClienteFake):
            def filme(self, imdb_id: str) -> tuple[TitleInfo, list[ServerOption]]:
                raise SourceError("título desconhecido")

        resolver = ResolverFake(mapa={"vidsrc": ["https://cdn/master.m3u8"]})
        fonte = MyEmbedSource(client=ClienteQueNaoConhece(), resolver=resolver)

        media = fonte.fetch("tt0098904")

        self.assertEqual([link.url for link in media.links], ["https://cdn/master.m3u8"])
        self.assertEqual(media.links[0].label, "VidSrc")

    def test_url_completa_aceita_tambem(self) -> None:
        cliente = ClienteFake(filme=(INFO_FILME, []))
        fonte = MyEmbedSource(client=cliente, resolver=ResolverFake())

        media = fonte.fetch("https://myembed.biz/filme/tt22084616")

        self.assertEqual(media.external_id, "tt22084616")
        self.assertEqual(cliente.ultimo_chamado, "tt22084616")

    def test_sem_options_sem_links(self) -> None:
        cliente = ClienteFake(filme=(INFO_FILME, []))
        fonte = MyEmbedSource(client=cliente, resolver=ResolverFake())

        media = fonte.fetch("tt22084616")

        self.assertEqual(media.links, [])


class SerieTest(unittest.TestCase):
    def test_episodio_resolve_links(self) -> None:
        cliente = ClienteFake(episodio=(INFO_FILME, OPTS_SERIE))
        resolver = ResolverFake(mapa={"blogger": ["https://cdn/ep1.mp4"]})
        fonte = MyEmbedSource(client=cliente, resolver=resolver)

        media = fonte.fetch_serie("30984", season=1, episode=1)

        self.assertEqual(media.kind, MediaKind.SERIES)
        eps = media.seasons[0].episodes
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].number, 1)
        self.assertEqual(eps[0].links[0].url, "https://cdn/ep1.mp4")
        self.assertIn("/30984/1/1", resolver.referer_recebido)


class SerieNaoSuportadaTest(unittest.TestCase):
    def test_base_levanta_not_implemented(self) -> None:
        class FonteSemSerie(Source):
            name: ClassVar[str] = "semserie"

            def fetch(self, external_id: str, **kwargs: object):
                raise AssertionError("não deveria ser chamado")

        with self.assertRaises(NotImplementedError):
            FonteSemSerie().fetch_serie("x")


class RegistryTest(unittest.TestCase):
    def _registry(self, cliente: ClienteFake) -> SourceRegistry:
        registry = SourceRegistry()
        registry.register(MyEmbedSource(client=cliente, resolver=ResolverFake()))
        return registry

    def test_registry_extrai_filme(self) -> None:
        registry = self._registry(ClienteFake(filme=(INFO_FILME, list(OPTS_FILME))))

        media = registry.extract("myembed", "tt22084616")

        self.assertEqual(media.external_id, "tt22084616")
        self.assertEqual(media.links, [])

    def test_names_inclui_myembed(self) -> None:
        registry = self._registry(ClienteFake())
        self.assertIn("myembed", registry.names())


if __name__ == "__main__":
    _ = unittest.main()
