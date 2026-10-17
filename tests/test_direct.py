import unittest

from sources.direct import extrair_url_blogger, extrair_url_watchplay, resposta_direta_e_definitiva
from sources.playerflix import ServerOption

HTML = (
    "<script>createMyPlayer({container:'#tv-player',id:\"tvchannel-5786\","
    "url:\"https:\\/\\/vid.exemplo.invalid\\/st\\/playlist.m3u8?md5=abc&expires=1\","
    "type:'m3u8',isLive:false});</script>"
)


class WatchPlayDiretoTest(unittest.TestCase):
    def test_extrai_link_da_pagina(self) -> None:
        self.assertEqual(
            extrair_url_watchplay(HTML),
            "https://vid.exemplo.invalid/st/playlist.m3u8?md5=abc&expires=1",
        )

    def test_pagina_sem_player_devolve_none(self) -> None:
        self.assertIsNone(extrair_url_watchplay("<html><body>nada</body></html>"))


class DefinitivoTest(unittest.TestCase):
    def test_watchplay_sem_link_nao_vai_ao_navegador(self) -> None:
        self.assertTrue(resposta_direta_e_definitiva(ServerOption(id="w", label="W", embed_url="https://v1.watchplay.shop/movie/tt1")))

    def test_outros_servidores_ainda_podem_cair_no_navegador(self) -> None:
        self.assertFalse(resposta_direta_e_definitiva(ServerOption(id="e", label="E", embed_url="https://embedplayer2.xyz/video/abc")))
        self.assertFalse(resposta_direta_e_definitiva(ServerOption(id="v", label="V", embed_url="https://vidsrc.to/embed/movie/tt1")))


if __name__ == "__main__":
    _ = unittest.main()


class TestExtrairUrlBlogger(unittest.TestCase):
    def test_escolhe_maior_qualidade_e_decodifica(self) -> None:
        resposta = (
            r'["https://rr3---sn-x.googlevideo.com/videoplayback?id=1\u0026itag\u003d18\u0026sig\u003dA",'
            r'"https://rr3---sn-x.googlevideo.com/videoplayback?id=1\u0026itag\u003d22\u0026sig\u003dB"]'
        )
        url = extrair_url_blogger(resposta)
        self.assertEqual(url, "https://rr3---sn-x.googlevideo.com/videoplayback?id=1&itag=22&sig=B")

    def test_sem_video_devolve_none(self) -> None:
        self.assertIsNone(extrair_url_blogger('["sem link"]'))
