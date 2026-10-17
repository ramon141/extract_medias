import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from sources.captcha import (
    CaptchaError,
    CapMonsterClient,
    DesafioTurnstile,
    capturar_desafio_turnstile,
)

HTML_VERIFICACAO = """
const form = document.getElementById('cff-x');
const status = document.getElementById('cfs-x');

// script da página de verificação
var turnstileSiteKey = "0x4AAAAAAFXwTSjbU-Kto1L5";
const turnstileChallengeCData = "sf_f31a78adfba1908b6be8258f26b59431fe3fbc9a7b7b7a2a";
window.turnstile.render(widgetBox, {
    sitekey: turnstileSiteKey,
    action: 'embed_access',
    cData: turnstileChallengeCData,
    theme: 'dark',
    retry: 'never',
    callback: window.cloudflareEmbedCaptchaPassed,
    'expired-callback': window.cloudflareEmbedCaptchaExpired
});
<form method="POST" action="https://superflixapi.fun/serie/tt0096697/1/1" id="cff-x" class="captcha-shell">
"""


@dataclass
class RespostaFake:
    dados: dict[str, Any]

    def json(self) -> object:
        return self.dados


class SessaoFalso:
    """Imita a sessão HTTP: createTask/getTaskResult com respostas programadas."""

    def __init__(self) -> None:
        self.respostas: list[dict[str, Any]] = []
        self.chamadas: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, json: object, timeout: float) -> RespostaFake:
        _ = timeout, json
        self.chamadas.append((url, {}))
        corpo = self.respostas.pop(0) if self.respostas else {"errorId": 22, "errorCode": "ERROR_TASK_ABSENT"}
        return RespostaFake(dados=corpo)


def sem_sono(segundos: object) -> None:
    """Substitui o sleep real nos testes de polling."""
    _ = segundos


def cliente_com_cronograma(respostas: list[dict[str, Any]]) -> tuple[CapMonsterClient, SessaoFalso]:
    sessao = SessaoFalso()
    sessao.respostas = respostas
    cliente = CapMonsterClient(client_key="chave-de-teste", session=sessao, timeout_total_ms=30_000)
    return cliente, sessao


class DesafioTest(unittest.TestCase):
    def test_extrai_sitekey_cdata_e_callback_do_html(self) -> None:
        desafio = capturar_desafio_turnstile(HTML_VERIFICACAO, "https://superflixapi.fun/serie/x/1/1")

        self.assertIsNotNone(desafio)
        assert desafio is not None
        self.assertEqual(desafio.website_key, "0x4AAAAAAFXwTSjbU-Kto1L5")
        self.assertEqual(desafio.website_data, "sf_f31a78adfba1908b6be8258f26b59431fe3fbc9a7b7b7a2a")
        self.assertEqual(desafio.action, "embed_access")

    def test_sem_captcha_devolve_none(self) -> None:
        self.assertIsNone(capturar_desafio_turnstile("<html><h1>Player</h1></html>", "https://x/y"))


class PayloadTest(unittest.TestCase):
    def test_payload_baseline(self) -> None:
        desafio = DesafioTurnstile(website_url="https://x/s/1/1", website_key="0xK")
        self.assertEqual(
            desafio.payload(),
            {"type": "TurnstileTaskProxyless", "websiteURL": "https://x/s/1/1", "websiteKey": "0xK"},
        )

    def test_payload_com_cdata_e_action(self) -> None:
        desafio = DesafioTurnstile(website_url="https://x/s/1/1", website_key="0xK", website_data="sf_x", action="a")
        payload = desafio.payload()
        self.assertEqual(payload.get("websiteData"), "sf_x")
        self.assertEqual(payload.get("action"), "a")


class ClienteTest(unittest.TestCase):
    def test_resolver_turnstile_cria_e_obtem_token(self) -> None:
        with patch("sources.captcha.time.sleep", sem_sono):
            cronograma: list[dict[str, Any]] = [
                {"errorId": 0, "taskId": 77},
                {"errorId": 0, "status": "processing"},
                {"errorId": 0, "status": "ready", "solution": {"token": "TOKEN_SOLVIDO"}},
            ]
            cliente, sessao = cliente_com_cronograma(cronograma)
            desafio = DesafioTurnstile(website_url="https://x/s/1/1", website_key="0xK")

            token = cliente.resolver_turnstile(desafio)

            self.assertEqual(token, "TOKEN_SOLVIDO")
        primeira_url, _ = sessao.chamadas[0]
        self.assertIn("createTask", primeira_url)
        resultado_url, _ = sessao.chamadas[-1]
        self.assertIn("getTaskResult", resultado_url)

    def test_erro_fatal_levanta_captcha_error(self) -> None:
        with patch("sources.captcha.time.sleep", sem_sono):
            cronograma: list[dict[str, Any]] = [
                {"errorId": 21, "errorCode": "ERROR_KEY_DOES_NOT_EXIST", "errorDescription": "chave inválida"}
            ]
            cliente, _ = cliente_com_cronograma(cronograma)
            with self.assertRaises(CaptchaError):
                cliente.resolver_turnstile(DesafioTurnstile(website_url="https://x", website_key="0xK"))

    def test_sem_chave_avisa_antes_de_tentar(self) -> None:
        cliente = CapMonsterClient(client_key="")
        with self.assertRaises(CaptchaError) as contexto:
            cliente.resolver_turnstile(DesafioTurnstile(website_url="https://x", website_key="0xK"))
        self.assertIn("CAPMONSTER_CLIENT_KEY", str(contexto.exception))

    def test_solution_sem_token_levanta_erro(self) -> None:
        with patch("sources.captcha.time.sleep", sem_sono):
            cronograma: list[dict[str, Any]] = [
                {"errorId": 0, "taskId": 1},
                {"errorId": 0, "status": "ready", "solution": {}},
            ]
            cliente, _ = cliente_com_cronograma(cronograma)
            with self.assertRaises(CaptchaError):
                cliente.resolver_turnstile(DesafioTurnstile(website_url="https://x", website_key="0xK"))


if __name__ == "__main__":
    _ = unittest.main()
