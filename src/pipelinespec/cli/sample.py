from pipelinespec.models import Sample
from pathlib import Path
import logging as log
import requests
import click
import json
import os

def fetch_github_repositories(n: int, page: int, headers: dict | None) -> list[dict]:

    url = 'https://api.github.com/search/repositories'

    exclude_topics = ['awesome-list', 'tutorial', 'template', 'list', 'certification', 'roadmap', 'interview', 'skills', 'deepseek']

    response = requests.get(url, params={
        'q': f'stars:>1000 archived:false fork:false topics:>0 -language:markdown {" ".join([f"-topic:{topic}" for topic in exclude_topics])} -org:deepseek -org:deepseek-ai',
        'sort': 'stars',
        'order': 'desc',
        'page': page,
        'per_page': n,
    }, headers=headers)

    if not response.ok:
        log.error('Failed to fetch GitHub repositories.')
        raise Exception(response.json())

    return response.json()['items']

def filter_repos(repositories: list[dict], headers: dict | None) -> list[Sample]:

    valid = []

    for repo in repositories:

        url = f'{repo["url"]}/contents/.github/workflows'

        response = requests.get(url, headers=headers)
        if not response.ok:
            log.warning(f'Failed to fetch workflows for {repo["url"]}')
            continue

        workflows = [workflow['path'] for workflow in response.json() if workflow['path'].endswith('.yml') or workflow['path'].endswith('.yaml')]

        valid.append(Sample(
            name=repo['name'],
            clone_url=repo['html_url'],
            api_url=repo['url'],
            workflows=workflows
        ))

    return valid

@click.command()
@click.option('-n', default=10, help='Number of repositories to fetch.')
@click.option('--output', '-o', default='data/', help='Output directory for samples GitHub repositories.')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging.')
def main(n: int, output: str, verbose: bool) -> None:

    if verbose:
        log.getLogger().setLevel(log.DEBUG)

    output = Path(output)
    if not os.path.exists(output):
        os.makedirs(output)

    request_headers = None
    if os.environ.get('GITHUB_TOKEN', None):
        log.debug('Using GitHub token.')
        request_headers = {
            'Authorization': f'token {os.environ["GITHUB_TOKEN"]}'
        }

    # Fetch repositories
    
    samples = []

    log.info(f'Fetching {n} valid GitHub repsitories...')

    i = 1
    while len(samples) < n and i <= 10:

        log.debug(f'Fetching page {i} of GitHub repositories...')

        raw_repos = fetch_github_repositories(n, i, request_headers)
        if verbose:
            with open(output / f'raw_repositories_{i}.json', 'w') as f:
                json.dump(raw_repos, f, indent=4)
        
        valid = filter_repos(raw_repos, request_headers)
        samples.extend(valid)

        i += 1

    # Save data

    log.info(f'{len(samples)} valid GitHub repositories have been fetched and processed.')
    if len(samples) < n:
        log.warning(f'Missing {n - len(samples)} required samples.')

    with open(output / 'samples.json', 'w') as f:
        json.dump([s.model_dump() for s in samples[:n]], f, indent=4)

    log.info(f'Samples saved to {output / "samples.json"}.')

if __name__ == '__main__':
    main()
