"""Resolve players de terceiro (options[] do playerflix) para mídia real.

Técnica: navega cada player com Playwright (Chromium real), escuta a rede e
captura requisições de vídeo (m3u8/mp4) que o player dispara ao iniciar.
Se o vídeo não inicia sozinho, tenta cliques nos seletores de play comuns.

Players testados e formatos observados:
    - WatchPlay (v1.watchplay.shop)  → playlist.m3u8 direto
    - EmbedPlayer (embedplayer2.xyz) → master.txt (HLS) + .mp4 (CDN)
    - EmbedPlay (embedplayabyss.top) → .mp4 (storage.googleapis)
    - Blogger (video.g?token=…)      → .mp4 após clique
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import requests

from sources.models import StreamKind
from sources.playerflix import ServerOption

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page, Request, ViewportSize

logger = logging.getLogger(__name__)

_VIEWPORT: ViewportSize = {"width": 1280, "height": 720}

_STREAM_RE = re.compile(
    "|".join(
        [
            # extensões diretas (HLS/DASH/MP4) e playlists HLS disfarçadas de .txt
            r"\.(m3u8|mp4|mpd)(?:\?|#|$)",
            r"/master\.txt(?:\?|#|$)",
            # CDNs tipo Google/YouTube: /videoplayback sem extensão
            r"/videoplayback(?:\?|#|$)",
            r"googlevideo\.com/",
            # player do Blogger: mídia sai por blogger.com/video/<id fragmentado>
            r"blogger\.com/video/",
        ]
    ),
    re.IGNORECASE,
)

_ANEXOS_GOOGLE = ("googlevideo.com", "blogger.com/video/", "/videoplayback")

_PLAY_SELECTORS = (
    "i.fa-play",
    ".play",
    ".jw-display-icon-container",
    "div.vjs-big-play-button",
    "video",
    "button",
)

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)


@dataclass
class ServerResult:
    """Resolução de um server: streams achados (ou avisos)."""

    option: ServerOption
    streams: list[str] = field(default_factory=list[str])
    avisos: list[str] = field(default_factory=list[str])


def extensao_midia(url: str) -> str | None:
    """Extensão/tipo de mídia numa URL ('m3u8' cobre master.txt; googlevideo = mp4)."""
    if not _STREAM_RE.search(url):
        return None
    url_minuscula = url.lower()
    match = re.search(r"\.(m3u8|mp4|mpd)", url_minuscula)
    if match:
        return match.group(1).lower()
    if "/master.txt" in url_minuscula:
        return "m3u8"  # master.txt é HLS disfarçado
    if any(anexo in url_minuscula for anexo in _ANEXOS_GOOGLE):
        return "mp4"
    return None


def _guess_resolution(url: str) -> str:
    match = re.search(r"(2160p|1080p|720p|480p)", url, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return "auto"


class PlaywrightServerResolver:
    """Abre os players com Playwright e captura as URLs de mídia real."""

    def __init__(
        self,
        timeout_ms: int = 25_000,
        click_after_ms: int = 8_000,
        max_cliques: int = 3,
        stop_after_first_stream: bool = True,
        verify: bool = True,
        verify_timeout: float = 15.0,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.click_after_ms = click_after_ms
        self.max_cliques = max_cliques
        self.stop_after_first_stream = stop_after_first_stream
        self.verify = verify
        self.verify_timeout = verify_timeout

    def resolve(self, options: list[ServerOption], referer: str = "") -> list[ServerResult]:
        """Resolve os servers em ordem; devolve um resultado por server tentado."""
        from playwright.sync_api import sync_playwright

        resultados: list[ServerResult] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            contexto = browser.new_context(
                user_agent=_DEFAULT_UA,
                viewport=_VIEWPORT,
                locale="pt-BR",
            )
            try:
                for option in options:
                    result = self._resolve_option(contexto, option, referer)
                    resultados.append(result)
                    if result.streams and self.stop_after_first_stream:
                        break
            finally:
                browser.close()

        if self.verify:
            for result in resultados:
                self._verify_streams(result)
        return resultados

    def _resolve_option(
        self, contexto: BrowserContext, option: ServerOption, referer: str
    ) -> ServerResult:
        """Carrega um player e captura as URLs de mídia que ele disparar."""
        resultado = ServerResult(option=option)
        streams: dict[str, None] = {}
        page = contexto.new_page()

        def on_request(request: Request) -> None:
            url = request.url
            if url in streams:
                return
            if extensao_midia(url):
                logger.debug("mídia capturada [%s]: %s", option.id, url[:140])
                streams[url] = None

        page.on("request", on_request)
        try:
            _ = page.goto(
                option.embed_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
                referer=referer or None,
            )
            inicio = time.monotonic()
            tentativas_click = 0
            while (time.monotonic() - inicio) * 1000 < self.timeout_ms:
                page.wait_for_timeout(1000)
                if streams:
                    page.wait_for_timeout(1000)  # deixa registar duplicados/qualidades
                    break
                decorrido_ms = (time.monotonic() - inicio) * 1000
                if decorrido_ms >= self.click_after_ms and tentativas_click < self.max_cliques:
                    self._click_play(page)
                    tentativas_click += 1
        except Exception as erro:  # noqa: BLE001 - resolver tolera falha por server
            resultado.avisos.append(f"{type(erro).__name__}: {erro}")
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass
        resultado.streams = list(streams)
        return resultado

    def _click_play(self, page: Page) -> None:
        """Tenta clicar em botões de play; último recurso: centro do player."""
        clicou = False
        for seletor in _PLAY_SELECTORS:
            try:
                if page.is_visible(seletor):
                    page.click(seletor, timeout=1500, force=True)
                    logger.debug("clicou em %s", seletor)
                    clicou = True
                    break
            except Exception as erro:  # noqa: BLE001
                logger.debug("click %s falhou: %s", seletor, erro)
        if not clicou:
            try:
                page.mouse.click(_VIEWPORT["width"] / 2, _VIEWPORT["height"] / 2)
                logger.debug("clicou no centro do player")
            except Exception as erro:  # noqa: BLE001
                logger.debug("click central ignorado: %s", erro)

    def _verify_streams(self, result: ServerResult) -> None:
        """Checa as URLs com um GET de 2 bytes para filtrar links mortos."""
        validos: list[str] = []
        for url in result.streams:
            try:
                resposta = requests.get(
                    url,
                    headers={"User-Agent": _DEFAULT_UA, "Range": "bytes=0-1"},
                    timeout=self.verify_timeout,
                    stream=True,
                )
                ok = resposta.status_code in (200, 206)
                resposta.close()
            except requests.RequestException as erro:
                logger.debug("verificação falhou: %s", erro)
                ok = False
            if ok:
                validos.append(url)
            else:
                result.avisos.append(f"link não respondem: {url[:110]}")
        removidos = [u for u in result.streams if u not in validos]
        if removidos:
            result.avisos.append(
                "removidos por verificação: " + ", ".join(u[:90] for u in removidos)
            )
        result.streams = validos


def links_do_resultado(result: ServerResult) -> list[tuple[str, str, StreamKind]]:
    """Converte streams achados em (url, resolution, kind)."""
    return [(url, _guess_resolution(url), StreamKind.STREAM) for url in result.streams]
