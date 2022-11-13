from episode import Episode


class Serie:
    def __init__(self, title='', abstract='', poster='') -> None:
        self.title = title
        self.abstract = abstract
        self.poster = poster
        self.seasons = {}

    def add_episode(self, season_number, release_date, images=[], name=''):
        episode = Episode(release_date, images, name)
        self.seasons[season_number].append(episode)

    def __str__(self) -> str:
        dictionary = {
            'title': self.title,
            'seasons': str(self.seasons)
        }

        return str(dictionary)
