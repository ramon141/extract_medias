import unittest

from sources.direct import extrair_url_watchplay

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


if __name__ == "__main__":
    _ = unittest.main()
