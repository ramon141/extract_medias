import requests


class Link:
    def __init__(self, link_video, resolution) -> None:
        self.link_video = link_video
        self.resolution = resolution
        self.status = self.test_link(link_video)

    def test_link(self, link_video) -> bool:
        response = requests.get(link_video)
        return response.status_code == 200

    def __str__(self) -> str:
        dictionary = {
            'link_video': self.link_video,
            'resolution': self.resolution,
            'status': self.status
        }

        return str(dictionary)
