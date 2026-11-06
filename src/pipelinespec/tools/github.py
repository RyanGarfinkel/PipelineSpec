from singleton_decorator import singleton
import requests
import os

SEARCH_URL = 'https://api.github.com/search/repositories'
EXCLUDED_TOPICS = ['awesome-list', 'tutorial', 'template', 'list', 'certification', 'roadmap', 'interview', 'skills', 'deepseek']
QUERY = f'stars:>1000 archived:false fork:false topics:>0 -language:markdown {" ".join(f"-topic:{topic}" for topic in EXCLUDED_TOPICS)} -org:deepseek -org:deepseek-ai'

@singleton
class GitHub:

    def search(self, page: int, per_page: int) -> list[dict]:

        response = requests.get(SEARCH_URL, params={'q': QUERY, 'sort': 'stars', 'order': 'desc', 'page': page, 'per_page': per_page}, headers=self.__headers(), timeout=30)

        if not response.ok:
            raise RuntimeError(f'The GitHub repository search failed ({response.status_code}): {response.text}')

        return response.json()['items']

    def languages(self, name: str) -> list[str]:

        response = requests.get(f'https://api.github.com/repos/{name}/languages', headers=self.__headers(), timeout=30)

        if not response.ok:
            raise RuntimeError(f'The languages of {name} could not be fetched ({response.status_code}): {response.text}')

        return list(response.json())

    def __headers(self) -> dict[str, str] | None:

        token = os.environ.get('GITHUB_TOKEN')

        return {'Authorization': f'token {token}'} if token else None

github = GitHub()
