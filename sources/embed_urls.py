"""Interpreta iframes/URLs/IDs e descobre qual fonte e conteúdo extrair.

Aceita:
    - o snippet inteiro do iframe
    - https://myembed.biz/filme/tt22084616
    - https://myembed.biz/serie/30984            (catálogo)
    - https://myembed.biz/serie/30984/1/1        (episódio direto)
    - https://playerflix.ink/filme/tt22084616    (o player real por trás do myembed)
    - ID cru: "tt22084616" (IMDb = filme) ou "30984" (TMDB = série)
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from sources.models import MediaKind
from sources.errors import SourceError

MYEMBED_HOSTS = frozenset({"myembed.biz"})
PLAYERFLIX_HOSTS = frozenset({"playerflix.ink", "www.playerflix.ink"})
SUPPORTED_HOSTS = MYEMBED_HOSTS | PLAYERFLIX_HOSTS

_IFRAME_SRC = re.compile(r"<iframe[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)


@dataclass(frozen=True)
class EmbedTarget:
    """Conteúdo alvo da extração."""

    external_id: str  # IMDb "tt…" para filme; TMDB numérico para série
    kind: MediaKind | None = None  # None quando só um ID cru foi informado
    season: int | None = None
    episode: int | None = None

    def require_movie(self) -> "EmbedTarget":
        if self.kind is MediaKind.SERIES:
            raise SourceError("Use --temporada/--episodio para séries, não para filmes.")
        return self


def parse_embed_url(alvo: str) -> EmbedTarget:
    """Extrai o alvo de um snippet de iframe, URL ou ID cru."""
    texto = alvo.strip()

    if "<iframe" in texto.lower():
        m = _IFRAME_SRC.search(texto)
        if not m:
            raise SourceError("Iframe sem atributo src.")
        texto = m.group(1).strip()

    if "://" in texto:
        return _parse_url(texto)

    return _parse_bare_id(texto)


def _parse_url(url: str) -> EmbedTarget:
    parsed = urlparse(url)
    host = parsed.netloc.lower().lstrip("www.")
    if not host or not parsed.path:
        raise SourceError(f"URL inválida: {url}")
    if host not in SUPPORTED_HOSTS:
        raise SourceError(f"Domínio não suportado: {host} (suportados: {sorted(SUPPORTED_HOSTS)})")

    segmentos = [s for s in parsed.path.split("/") if s]
    if not segmentos:
        raise SourceError(f"URL sem conteúdo: {url}")

    primeiro = segmentos[0].lower()
    identificador = segmentos[1] if len(segmentos) > 1 else ""

    # /filme/tt22084616  (também aceita /filmes/, /movie/)
    if primeiro in ("filme", "filmes", "movie"):
        if not re.fullmatch(r"tt\d+", identificador):
            raise SourceError(f"URL de filme deve usar IMDb ID (tt…): {url}")
        return EmbedTarget(external_id=identificador, kind=MediaKind.MOVIE)

    # /serie/30984/1/1  ou /tv/30984/1/1
    if primeiro in ("serie", "series", "tv"):
        if not identificador.isdigit():
            raise SourceError(f"URL de série deve usar TMDB ID numérico: {url}")
        temporada, episodio = _parse_temporada_episodio(segmentos[2:], url)
        return EmbedTarget(
            external_id=identificador,
            kind=MediaKind.SERIES,
            season=temporada,
            episode=episodio,
        )

    raise SourceError(f"Caminho não reconhecido: {url}")


def _parse_temporada_episodio(segmentos: list[str], url: str) -> tuple[int | None, int | None]:
    """Fim da URL pode ser vazia (catálogo), /temporada ou /temporada/episodio."""
    match len(segmentos):
        case 0:
            return None, None
        case 1:
            if not segmentos[0].isdigit():
                raise SourceError(f"Temporada inválida: {url}")
            return int(segmentos[0]), None
        case _:
            if not (segmentos[0].isdigit() and segmentos[1].isdigit()):
                raise SourceError(f"Temporada/episódio inválidos: {url}")
            return int(segmentos[0]), int(segmentos[1])


def _parse_bare_id(identificador: str) -> EmbedTarget:
    if re.fullmatch(r"tt\d+", identificador):
        return EmbedTarget(external_id=identificador, kind=MediaKind.MOVIE)
    if identificador.isdigit():
        # TMDB numérico: pode ser filme ou série, o chamador decide
        return EmbedTarget(external_id=identificador, kind=None)
    raise SourceError(f"ID não reconhecido: {identificador} (use 'tt…' para filme ou dígitos para série)")


def forcar_serie(alvo: EmbedTarget) -> EmbedTarget:
    """Trata um ID numérico cru como TMDB de série."""
    return EmbedTarget(
        external_id=alvo.external_id,
        kind=MediaKind.SERIES,
        season=alvo.season,
        episode=alvo.episode,
    )
