from dataclasses import dataclass, field
from enum import Enum


class MediaKind(Enum):
    MOVIE = "movie"
    SERIES = "series"


class StreamKind(Enum):
    """`EMBED` é o player de terceiro (iframe); `STREAM` é mídia direta (m3u8/mp4)."""

    EMBED = "embed"
    STREAM = "stream"


@dataclass(frozen=True)
class StreamLink:
    url: str
    resolution: str
    label: str = ""
    kind: StreamKind = StreamKind.STREAM


@dataclass
class Episode:
    number: int
    name: str = ""
    release_date: str = ""
    poster: str = ""
    links: list[StreamLink] = field(default_factory=list[StreamLink])


@dataclass
class Season:
    number: int
    name: str = ""
    release_date: str = ""
    episodes: list[Episode] = field(default_factory=list[Episode])


@dataclass
class Media:
    external_id: str
    title: str
    kind: MediaKind
    abstract: str = ""
    poster: str = ""
    title_en: str = ""
    release_date: str = ""
    links: list[StreamLink] = field(default_factory=list[StreamLink])
    seasons: list[Season] = field(default_factory=list[Season])
