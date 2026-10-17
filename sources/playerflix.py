"""Cliente HTTP da API Ajax do playerflix.ink.

O iframe de myembed.biz é só um wrapper: ele injeta o player real de
playerflix.ink, que por sua vez consulta ``inc/Ajax.php`` para descobrir
quais servers têm o vídeo (WatchPlay, EmbedPlayer, Blogger, Superflix…).

Endpoints descobertos por análise da rede:
    GET /inc/Ajax.php?type=movie&id={imdb}&season=null&episode=null
    GET /inc/Ajax.php?type=tv&id={tmdb}&season={s}&episode={e|null}

A resposta é JSON com metadados do título (TMDB) e ``options[]`` com os
players de terceiros que entregam o vídeo.
"""

import re
from dataclasses import dataclass
from typing import Protocol, cast

import requests

from sources.errors import SourceError
from sources.models import Episode, Season

AJAX_URL = "https://playerflix.ink/inc/Ajax.php"
POSTER_TMDB = "https://media.themoviedb.org/t/p/original"

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Referer": "https://playerflix.ink/",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

_BUDGET_OK = frozenset({"success"})

_JsonDict = dict[str, object]
_JsonList = list[_JsonDict]


class RespostaProtocol(Protocol):
    """Assinatura mínima da resposta (requests.Response ou fake dos testes)."""

    def json(self) -> object: ...

    def raise_for_status(self) -> None: ...


class SessaoProtocol(Protocol):
    """Assinatura mínima usada do requests.Session (facilita testes com fakes)."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> RespostaProtocol:
        ...


def _dict(valor: object) -> _JsonDict:
    """Garante um dict[str, Any] para acessar JSON."""
    return cast(_JsonDict, valor) if isinstance(valor, dict) else {}


def _dicts(valor: object) -> _JsonList:
    """Garante uma lista de dicts para iterar JSON."""
    if not isinstance(valor, list):
        return []
    convertidos = [_dict(item) for item in cast(list[object], valor)]
    return [item for item in convertidos if item]


def _str(valor: object) -> str:
    """Strings vindas do JSON; outras coisas viram vazio."""
    return valor if isinstance(valor, str) else ""


def _int(valor: object) -> int:
    """Inteiros vindos do JSON; outras coisas viram zero."""
    return valor if isinstance(valor, int) else 0


@dataclass(frozen=True)
class ServerOption:
    """Um player de terceiro disponível para o título/episódio."""

    id: str  # ex.: "watchplay", "embedplayer", "blogger"
    label: str  # ex.: "WatchPlay"
    embed_url: str
    lang: str = ""
    healthy: bool = True  # "budget" == success na resposta da API


@dataclass(frozen=True)
class TitleInfo:
    title: str
    title_en: str = ""
    poster: str = ""  # imagem de fundo/poster servida pelo TMDB
    release_date: str = ""
    tmdb_id: str = ""


def _tmdb_image(path: str) -> str:
    """Caminhos de imagem do TMDB podem vir relativos."""
    path = path or ""
    return path if path.startswith("http") else f"{POSTER_TMDB}{path}"


def _title_info(data: _JsonDict) -> TitleInfo:
    title = _dict(data.get("title"))
    return TitleInfo(
        title=_str(title.get("pt")) or _str(title.get("en")),
        title_en=_str(title.get("en")),
        poster=_tmdb_image(_str(data.get("bgImage"))),
        release_date=_str(data.get("release_date")),
        tmdb_id=str(_int(data.get("id")) or ""),
    )


def _options(data: _JsonDict) -> list[ServerOption]:
    saida: list[ServerOption] = []
    vistos: set[str] = set()
    for opt in _dicts(data.get("options")):
        embed = _str(opt.get("embed")).strip()
        if not re.match(r"^https?://", embed):
            continue
        identificador = _str(opt.get("id")) or _str(opt.get("label")) or "desconhecido"
        deduplicar = f"{identificador}|{embed}"
        if deduplicar in vistos:
            continue
        vistos.add(deduplicar)
        saida.append(
            ServerOption(
                id=identificador,
                label=_str(opt.get("label")) or identificador,
                embed_url=embed,
                lang=_str(opt.get("lang")),
                healthy=(_str(opt.get("budget")) or "success") in _BUDGET_OK,
            )
        )
    # players saudáveis e em pt-br primeiro; sort é estável, preserva a ordem da API
    saida.sort(key=lambda o: (not o.healthy, o.lang != "pt-br"))
    return saida


class PlayerFlixClient:
    """Consome a API Ajax do playerflix.ink."""

    def __init__(
        self,
        session: SessaoProtocol | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.sessao = session or requests.Session()
        self.headers = dict(DEFAULT_HEADERS)
        if headers:
            self.headers.update(headers)
        self.timeout = timeout

    def _ajax(
        self,
        tipo: str,
        identificador: str,
        temporada: str = "null",
        episodio: str = "null",
    ) -> _JsonDict:
        resposta = self.sessao.get(
            AJAX_URL,
            params={"type": tipo, "id": identificador, "season": temporada, "episode": episodio},
            headers=self.headers,
            timeout=self.timeout,
        )
        resposta.raise_for_status()
        dados = _dict(resposta.json())
        if not dados.get("status"):
            mensagem = _str(dados.get("message")) or "sem dados"
            raise SourceError(f"Ajax recusou a busca ({mensagem}): type={tipo} id={identificador}")
        return _dict(dados.get("data"))

    def filme(self, imdb_id: str) -> tuple[TitleInfo, list[ServerOption]]:
        """Filme por IMDb ID (tt…)."""
        data = self._ajax("movie", imdb_id)
        return _title_info(data), _options(data)

    def temporada_episodio(
        self,
        tmdb_id: str,
        temporada: int | None,
        episodio: int | None,
    ) -> tuple[TitleInfo, list[ServerOption]]:
        """Servers de um episódio (ou da "página" do título quando sem s/e)."""
        season_param = str(temporada) if temporada is not None else "null"
        episode_param = str(episodio) if episodio is not None else "null"
        data = self._ajax("tv", tmdb_id, season_param, episode_param)
        return _title_info(data), _options(data)

    def catalogo(self, tmdb_id: str) -> tuple[TitleInfo, dict[int, Season]]:
        """Catálogo completo de temporadas/episódios de uma série (sem links)."""
        data = self._ajax("tv", tmdb_id)
        info = _title_info(data)
        temporadas: dict[int, Season] = {}
        for season_data in _dicts(data.get("seasons")):
            numero = _int(season_data.get("season_number"))
            episodios = [
                Episode(
                    number=_int(ep_data.get("episode_number")),
                    release_date=_str(ep_data.get("release_date")),
                    poster=_tmdb_image(_str(_dict(ep_data.get("images")).get("poster"))),
                )
                for ep_data in _dicts(season_data.get("episodes"))
            ]
            temporadas[numero] = Season(
                number=numero,
                release_date=_str(season_data.get("release_date")),
                episodes=episodios,
            )
        return info, temporadas
