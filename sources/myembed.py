"""Fonte "myembed": o wrapper myembed.biz / playerflix.ink.

``myembed.biz/filme/tt22084616`` é um iframe que injeta o player real de
``playerflix.ink``; este Source fala direto com a API dele:

- filme: ``fetch("tt22084616")`` → Media com links dos servers
- série: ``fetch_serie("30984", season, episode)``
    - com temporada e episódio → links dos servers do episódio
    - sem os dois → catálogo completo de temporadas/episódios

Aceita também a URL/iframe completa no lugar do ID.
"""

import logging
from collections.abc import Callable
from typing import ClassVar

from sources.base import Source
from sources.direct import tem_caminho_direto
from sources.embed_urls import EmbedTarget, parse_embed_url
from sources.errors import SourceError
from sources.models import Episode, Media, MediaKind, Season, StreamLink
from sources.playerflix import PlayerFlixClient, ServerOption, TitleInfo
from sources.resolver import PlaywrightServerResolver, links_do_resultado

logger = logging.getLogger(__name__)

_VIDSRC = "https://vidsrc.to/embed"
_WATCHPLAY = "https://v1.watchplay.shop"


def _com_extras(options: list[ServerOption], watchplay: str, vidsrc: str) -> list[ServerOption]:
    """Servidores que não dependem do playerflix, tentados depois dos que ele lista.

    O WatchPlay (rápido, sem navegador) só entra se o playerflix não o listou; ele também
    aceita o código IMDb de séries, que o playerflix nem sempre conhece. O VidSrc é o último.
    """
    extras: list[ServerOption] = []
    if not any(option.id == "watchplay" for option in options):
        extras.append(ServerOption(id="watchplay", label="WatchPlay", embed_url=f"{_WATCHPLAY}/{watchplay}"))
    extras.append(ServerOption(id="vidsrc", label="VidSrc", embed_url=f"{_VIDSRC}/{vidsrc}"))
    return [*options, *extras]


class MyEmbedSource(Source):
    name: ClassVar[str] = "myembed"

    def __init__(
        self,
        client: PlayerFlixClient | None = None,
        resolver: PlaywrightServerResolver | None = None,
    ) -> None:
        self.client = client or PlayerFlixClient()
        self.resolver = resolver or PlaywrightServerResolver()

    def fetch(self, external_id: str, **_: object) -> Media:
        """Filme por IMDb ID (tt…), aceitando URL/iframe do embed."""
        alvo: EmbedTarget = parse_embed_url(external_id)
        if alvo.kind is not None and alvo.kind is not MediaKind.MOVIE:
            raise SourceError("Esse alvo é de série: use fetch_serie().")
        info, options = self._consultar(lambda: self.client.filme(alvo.external_id))
        options = _com_extras(options, f"movie/{alvo.external_id}", f"movie/{alvo.external_id}")
        return Media(
            external_id=alvo.external_id,
            title=info.title,
            kind=MediaKind.MOVIE,
            poster=info.poster,
            title_en=info.title_en,
            release_date=info.release_date,
            links=self._ligar(options, referer=f"https://playerflix.ink/filme/{alvo.external_id}"),
        )

    def fetch_serie(
        self,
        external_id: str,
        season: int | None = None,
        episode: int | None = None,
        **_: object,
    ) -> Media:
        """Série por TMDB ID: episódio específico ou catálogo completo."""
        if season is not None and episode is not None:
            info, options = self._consultar(
                lambda: self.client.temporada_episodio(external_id, season, episode)
            )
            options = _com_extras(
                options,
                f"tvshow/{external_id}/{season}/{episode}",
                f"tv/{external_id}/{season}/{episode}",
            )
            links = self._ligar(
                options,
                referer=f"https://playerflix.ink/serie/{external_id}/{season}/{episode}",
            )
            episode_info = Episode(number=episode, links=links)
            return Media(
                external_id=external_id,
                title=info.title,
                kind=MediaKind.SERIES,
                poster=info.poster,
                title_en=info.title_en,
                release_date=info.release_date,
                seasons=[Season(number=season, episodes=[episode_info])],
            )
        info, temporadas = self.client.catalogo(external_id)
        return Media(
            external_id=external_id,
            title=info.title,
            kind=MediaKind.SERIES,
            poster=info.poster,
            title_en=info.title_en,
            release_date=info.release_date,
            seasons=sorted(temporadas.values(), key=lambda s: s.number),
        )

    def _consultar(
        self, consulta: Callable[[], tuple[TitleInfo, list[ServerOption]]]
    ) -> tuple[TitleInfo, list[ServerOption]]:
        """O playerflix nem conhece todo título; sem ele ainda dá para tentar os servidores extras."""
        try:
            return consulta()
        except SourceError as erro:
            logger.warning("playerflix não listou servidores (%s); tentando só os extras", erro)
            return TitleInfo(title=""), []

    def _ligar(self, options: list[ServerOption], referer: str) -> list[StreamLink]:
        """Resolve os servers para mídia real; sem vídeo, devolve lista vazia.

        Servers que o próprio playerflix marca como indisponíveis são pulados:
        só gastavam o tempo limite sem entregar vídeo.
        """
        links: list[StreamLink] = []
        # sem navegador primeiro: o resultado rápido não espera o Blogger/VidSrc (sort estável)
        options = sorted((option for option in options if option.healthy), key=lambda o: not tem_caminho_direto(o))
        if not options:
            return links
        for result in self.resolver.resolve(options, referer=referer):
            for url, resolution in links_do_resultado(result):
                links.append(StreamLink(url=url, resolution=resolution, label=result.option.label))
            for aviso in result.avisos:
                logger.warning("[%s] %s", result.option.id, aviso)
        return links
