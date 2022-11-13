class Season:
    def __init__(self, episodes=[], season_number=-1, poster='') -> None:
        self.poster = poster
        self.season_number = season_number
        self.episodes = episodes

    def __str__(self) -> str:
        dictionary = {
            'poster': self.poster,
            'season_number': self.season_number,
            'episodes': str(self.episodes),
        }

        return str(dictionary)
