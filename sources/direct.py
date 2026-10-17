"""Caminho rápido: pega o link do vídeo por HTTP, sem navegador.

Vale para players que entregam o link na própria página ou por uma chamada
simples. Os demais (Blogger, que exige um clique; Abyss, atrás de desafio do
Cloudflare; VidSrc, que decifra no navegador) continuam no resolver com Playwright.
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
# o JSON do FirePlayer traz um campo "ck" com escapes inválidos: lemos só os campos úteis
_FIREPLAYER_CAMPO = r'"{campo}":"([^"]+)"'

_BLOGGER_TOKEN = re.compile(r"[?&]token=([\w-]+)")
_BLOGGER_VIDEO = re.compile(r"https://[^\"\\\s]*googlevideo\.com/videoplayback[^\"\\\s]*")
_BLOGGER_ITAG = re.compile(r"[?&]itag=(\d+)")
# itags do Google: 37=1080p, 22=720p, 59=480p, 18=360p
_BLOGGER_ORDEM = {37: 4, 22: 3, 59: 2, 18: 1}

# conexões reaproveitadas entre pedidos (o addon fica no ar), sem repetir o TLS
_sessao = requests.Session()


def extrair_url_watchplay(html: str) -> str | None:
    """Link do vídeo escrito na chamada do player do WatchPlay."""
    achado = _WATCHPLAY_URL.search(html)
    if not achado:
        return None
    url: object = json.loads(achado.group(1))
    return url if isinstance(url, str) and url.startswith("http") else None


def extrair_url_fireplayer(resposta: str) -> str | None:
    """Link HLS assinado (ou o master simples) da resposta do FirePlayer."""
    for campo in ("securedLink", "videoSource"):
        achado = re.search(_FIREPLAYER_CAMPO.format(campo=campo), resposta)
        if achado:
            return achado.group(1).replace("\\/", "/")
    return None


def _watchplay(option: ServerOption, referer: str, timeout: float) -> str | None:
    headers = dict(_HEADERS)
    if referer:
        headers["Referer"] = referer
    resposta = _sessao.get(option.embed_url, headers=headers, timeout=timeout)
    resposta.raise_for_status()
    return extrair_url_watchplay(resposta.text)


def _embedplayer(option: ServerOption, referer: str, timeout: float) -> str | None:
    """EmbedPlayer (FirePlayer): POST em /player/index.php devolve o link do vídeo."""
    partes = urlparse(option.embed_url)
    identificador = partes.path.rstrip("/").rsplit("/", 1)[-1]
    if not identificador:
        return None
    resposta = _sessao.post(
        f"{partes.scheme}://{partes.netloc}/player/index.php",
        params={"data": identificador, "do": "getVideo"},
        data={"hash": identificador, "r": referer},
        headers={"User-Agent": _UA, "Referer": option.embed_url, "X-Requested-With": "XMLHttpRequest"},
        timeout=timeout,
    )
    resposta.raise_for_status()
    return extrair_url_fireplayer(resposta.text)


def extrair_url_blogger(resposta: str) -> str | None:
    """Link de maior qualidade na resposta de dados do player do Blogger."""
    texto = resposta.replace("\\\\u003d", "=").replace("\\\\u0026", "&")
    texto = texto.replace("\\u003d", "=").replace("\\u0026", "&").replace("\\/", "/")

    def qualidade(url: str) -> int:
        itag = _BLOGGER_ITAG.search(url)
        return _BLOGGER_ORDEM.get(int(itag.group(1)), 0) if itag else 0

    links = _BLOGGER_VIDEO.findall(texto)
    return max(links, key=qualidade) if links else None


def _blogger(option: ServerOption, referer: str, timeout: float) -> str | None:
    """Blogger: a página só traz a chave da sessão; o link vem de uma chamada de dados (sem navegador)."""
    token = _BLOGGER_TOKEN.search(option.embed_url)
    if not token:
        return None
    pagina = _sessao.get(
        option.embed_url, headers={"User-Agent": _UA, "Referer": referer or "https://playerflix.ink/"}, timeout=timeout
    )
    pagina.raise_for_status()
    sessao = re.search(r'"FdrFJe":"(-?\d+)"', pagina.text)
    versao = re.search(r'"cfb2h":"([^"]+)"', pagina.text)
    if not sessao or not versao:
        return None
    pedido = json.dumps([[["WcwnYd", json.dumps([token.group(1), None, 0]), None, "generic"]]], separators=(",", ":"))
    resposta = _sessao.post(
        "https://www.blogger.com/_/BloggerVideoPlayerUi/data/batchexecute",
        params={"rpcids": "WcwnYd", "source-path": "/video.g", "f.sid": sessao.group(1), "bl": versao.group(1), "hl": "pt-BR", "rt": "c"},
        data={"f.req": pedido},
        headers={"User-Agent": _UA, "Referer": "https://www.blogger.com/", "X-Same-Domain": "1"},
        timeout=timeout,
    )
    resposta.raise_for_status()
    return extrair_url_blogger(resposta.text)


def resposta_direta_e_definitiva(option: ServerOption) -> bool:
    """WatchPlay escreve o link na página: se ela não tem, o navegador também não acharia.

    Nos demais (ex.: EmbedPlayer) a falha do caminho direto ainda pode ser contornada no navegador.
    """
    return urlparse(option.embed_url).netloc.lower().endswith("watchplay.shop")


def tem_caminho_direto(option: ServerOption) -> bool:
    """True para os players por HTTP cujo link serve a qualquer rede (o do Blogger prende à rede de quem pediu)."""
    host = urlparse(option.embed_url).netloc.lower()
    return host.endswith("watchplay.shop") or (host.startswith("embedplayer") and "/video/" in option.embed_url)


def url_direta(option: ServerOption, referer: str, timeout: float = 15.0) -> str | None:
    """Link do vídeo sem abrir navegador; None quando o player não permite."""
    host = urlparse(option.embed_url).netloc.lower()
    if host.endswith("watchplay.shop"):
        return _watchplay(option, referer, timeout)
    if host.startswith("embedplayer") and "/video/" in option.embed_url:
        return _embedplayer(option, referer, timeout)
    if host.endswith("blogger.com") and "token=" in option.embed_url:
        return _blogger(option, referer, timeout)
    return None
