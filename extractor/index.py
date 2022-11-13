from selenium import webdriver
from media.serie.index import Serie
import re
import requests
from constants import *


class Extractor:

    def __init__(self, base_url, regex_links, regex_infos, regex_infos_episode) -> None:
        self.browser = webdriver.Chrome()
        self.base_url = base_url
        self.regex_links = regex_links
        self.regex_infos = regex_infos
        self.regex_infos_episode = regex_infos_episode
        self.media = Serie()

    def get_page(url) -> str:
        response = requests.get(url)
        return response.content

    def extract(self) -> str:
        self.extract_recursion(0, self.base_url)
        return self.__str__()

    def extract_recursion(self, counter, url, html_history=[], image_episode=None, name_episode=None, release_date_episode=None, season_episode=None, episode_number=None):
        html = self.get_page(url)
        results = re.findall(self.regex_links[counter], html)
        self.getInfosAnime(i, html)
        html_history.append(array(url, html))

    def get_infos(self, counter, html):
        for regexInfo in self.regexInfosAnime:
            if (regexInfo[1] == counter):
                results = re.findall(self.regexInfo[0], html)

                if (regexInfo[2] == REGEX_NOME_MEDIA):
                    self.media.title = self.get_result(results, regexInfo)

                elif (regexInfo[2] == REGEX_POSTER):
                    self.media.poster = self.get_result(results, regexInfo)

                elif (regexInfo[2] == REGEX_SINOPSE):
                    self.media.abstract = self.get_result(results, regexInfo)

    def __str__(self) -> str:
        dictionary = {
            'base_url': self.base_url,
            'regex_links': self.regex_links,
            'regex_infos': self.regex_infos,
            'regex_infos_episode': self.regex_infos_episode
        }

        return str(dictionary)
