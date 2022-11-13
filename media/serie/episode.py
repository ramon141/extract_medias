from link import Link


class Episode:
    def __init__(self, release_date, images=[], name='') -> None:
        self.images = images
        self.name = name
        self.release_date = release_date
        self.links = []

    def add_link(self, link_video, resolution) -> None:
        link = Link(link_video, resolution)
        self.links.append(link)

    def __str__(self) -> str:
        dictionary = {
            'images': self.images,
            'name': self.name,
            'release_date': self.release_date,
            'links': str(self.links)
        }

        return str(dictionary)
