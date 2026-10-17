"""Cliente do CapMonster Cloud: resolve captchas para passar pela verificação.

Descobrimos que o server Premium (superflixapi) escolta o player com um
Cloudflare Turnstile (página "Verificação"):

    turnstileSiteKey        = 0x4AAAAAAFXwTSjbU-Kto1L5
    turnstileChallengeCData = sf_…   (render na página)
    callback                = window.cloudflareEmbedCaptchaPassed(token)
                              → <input name="cf-turnstile-response"> + form.submit()

A API do CapMonster Cloud usada (REST puro, sem cliente extra):
    POST https://api.capmonster.cloud/createTask
    POST https://api.capmonster.cloud/getTaskResult
    task: TurnstileTaskProxyless (websiteURL + websiteKey [, websiteData=cData])
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol, cast

import requests

from sources.config import carregar_env, variavel

logger = logging.getLogger(__name__)

CREATE_URL = "https://api.capmonster.cloud/createTask"
RESULT_URL = "https://api.capmonster.cloud/getTaskResult"

SONDA_MS = 2_000  # intervalo entre getTaskResult
ENCERRA_MS = 180_000  # teto total do solve

_ERROS_FATAIS = frozenset(
    {
        "ERROR_KEY_DOES_NOT_EXIST",
        "ERROR_ZERO_BALANCE",
        "ERROR_BAD_DUPLICATES",
        "ERROR_WRONG_SITEKEY",
        "ERROR_UNSUPPORTED_TYPE",
        "ERROR_SCOPE_USER_LIMIT",
        "ERROR_TASK_ABSENT",
    }
)


class CaptchaError(RuntimeError):
    """Falha na resolução do captcha (credencial, saldo ou execução)."""


@dataclass(frozen=True)
class DesafioTurnstile:
    """O que o CapMonster precisa para gerar o token do widget."""

    website_url: str
    website_key: str
    # o widget renderiza com cData (payload próprio do servidor); a API aceita
    # como extra via "websiteData" nas versões recentes
    website_data: str = ""
    action: str = ""

    def payload(self) -> dict[str, str]:
        dados: dict[str, str] = {
            "type": "TurnstileTaskProxyless",
            "websiteURL": self.website_url,
            "websiteKey": self.website_key,
        }
        if self.website_data:
            dados["websiteData"] = self.website_data
        if self.action:
            dados["action"] = self.action
        return dados


class RespostaCapMonster(Protocol):
    """Assinatura mínima da resposta HTTP (requests.Response ou fake)."""

    def json(self) -> object: ...


class SessaoCapMonster(Protocol):
    """Só o que o cliente usa do requests (facilita os fakes dos testes)."""

    def post(self, url: str, json: object, timeout: float) -> RespostaCapMonster:  # noqa: A002
        ...


def _payload_resposta(dados: object) -> dict[str, object]:
    if isinstance(dados, dict):
        return cast("dict[str, object]", dados)
    raise CaptchaError(f"Resposta inesperada do CapMonster: {dados!r}")


class CapMonsterClient:
    """Resolve Turnstile (e afins) via CapMonster Cloud."""

    def __init__(
        self,
        client_key: str | None = None,
        session: SessaoCapMonster | None = None,
        timeout_total_ms: int = ENCERRA_MS,
    ) -> None:
        carregar_env()
        self.client_key = client_key or variavel("CAPMONSTER_CLIENT_KEY") or variavel("CAPMONSTER_API_KEY")
        self.sessao = session or requests.Session()
        self.timeout_total_ms = timeout_total_ms

    @property
    def configurado(self) -> bool:
        return bool(self.client_key)

    def _post(self, url: str, corpo: dict[str, object]) -> dict[str, object]:
        resposta = self.sessao.post(url, json={"clientKey": self.client_key, **corpo}, timeout=30.0)
        dados = _payload_resposta(resposta.json())
        if not dados.get("errorId"):
            return dados
        codigo = str(dados.get("errorCode") or "ERROR_DESCONHECIDO")
        descricao = str(dados.get("errorDescription") or "")
        prefixo = "CapMonster (fatal): " if codigo in _ERROS_FATAIS else "CapMonster: "
        raise CaptchaError(f"{prefixo}{codigo} — {descricao}")

    def resolver_turnstile(self, desafio: DesafioTurnstile) -> str:
        """Cria a task e faz polling do resultado até sair o token."""
        if not self.configurado:
            raise CaptchaError(
                "CAPMONSTER_CLIENT_KEY ausente: coloque a chave da sua conta capmonster.cloud no arquivo .env do projeto."
            )
        criado = self._post(CREATE_URL, {"task": desafio.payload()})
        task_id = criado.get("taskId")
        if not isinstance(task_id, int):
            raise CaptchaError(f"taskId inválido na resposta: {criado!r}")
        logger.debug("task criada taskId=%s", task_id)

        inicio = time.monotonic()
        while (time.monotonic() - inicio) * 1000 < self.timeout_total_ms:
            time.sleep(SONDA_MS / 1000)
            resultado = self._post(RESULT_URL, {"taskId": task_id})
            if resultado.get("status") == "processing":
                continue
            solução = resultado.get("solution")
            if not isinstance(solução, dict):
                raise CaptchaError(f"solution ausente: {resultado!r}")
            token = cast("dict[str, object]", solução).get("token")
            if isinstance(token, str) and token:
                logger.debug("token resolvido (%d chars)", len(token))
                return token
            raise CaptchaError(f"solution sem token: {resultado!r}")
        raise CaptchaError(f"Tempo esgotado aguardando taskId={task_id}")


_PADRAO_SITEKEY = (
    r'turnstileSiteKey\s*=\s*"([^"]+)"'
    r'|data-sitekey\s*=\s*"([^"]+)"'
    r'|sitekey["\']?\s*[:=]\s*["\'](0x[\w-]+)["\']'
)


def capturar_desafio_turnstile(html: str, url_pagina: str) -> DesafioTurnstile | None:
    """Extrai sitekey/cData do HTML da página de verificação; None se lá não há captcha."""
    sitio = _primeiro(_PADRAO_SITEKEY, html)
    if not sitio:
        return None
    cdata = _primeiro(r'turnstileChallengeCData\s*=\s*"([^"]+)"', html) or ""
    return DesafioTurnstile(website_url=url_pagina, website_key=sitio, website_data=cdata, action="embed_access")


def _primeiro(padrao: str, texto: str) -> str | None:
    grupos = re.search(padrao, texto)
    if not grupos:
        return None
    for grupo in grupos.groups():
        if grupo:
            return grupo
    return None
