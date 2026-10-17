"""Caminho rápido: pega o link do vídeo direto do HTML do player, sem navegador.

Só vale para players que escrevem o link na própria página. Os demais
(ex.: Blogger, que exige um clique) continuam no resolver com Playwright.
"""

import json
import re
from urllib.parse import urlparse

import requests

from sources.playerflix import ServerOption

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)

# sem Sec-Fetch-* o WatchPlay esconde o link da página
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Sec-Fetch-Dest": "iframe",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
}

_WATCHPLAY_URL = re.compile(r'createMyPlayer\(\{.*?\burl:("(?:[^"\\]|\\.)*")', re.DOTALL)


def extrair_url_watchplay(html: str) -> str | None:
    """Link do vídeo escrito na chamada do player do WatchPlay."""
    achado = _WATCHPLAY_URL.search(html)
    if not achado:
        return None
    url: object = json.loads(achado.group(1))
    return url if isinstance(url, str) and url.startswith("http") else None


def url_direta(option: ServerOption, referer: str, timeout: float = 15.0) -> str | None:
    """Link do vídeo sem abrir navegador; None quando o player não permite."""
    host = urlparse(option.embed_url).netloc.lower()
    if not host.endswith("watchplay.shop"):
        return None
    headers = dict(_HEADERS)
    if referer:
        headers["Referer"] = referer
    resposta = requests.get(option.embed_url, headers=headers, timeout=timeout)
    resposta.raise_for_status()
    return extrair_url_watchplay(resposta.text)
