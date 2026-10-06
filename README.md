# PipelineSpec

## Dependencies

This project requires [act](https://nektosact.com/installation/index.html) to run GitHub Actions jobs and workflows locally. Act needs [Docker](https://www.docker.com/) to run them in images and PipelineSpec needs Docker to trace network calls and file access. The docker image used is [here](./src/pipelinespec/docker/Dockerfile).

## Sampling

The following command fetches `n` public GitHub repositories with at least one workflow file. You can set the number of samples to get by adding a `-n` flag (default 10), and use verbose logging by including the `-v` flag (default false). The resuling `samples.json` file will be stored in a `data/` directory created in the current working directrory by default, but can be specified with the `-o` flag.

```bash
uv run sample
```

It is reccomended to setup a GitHub [Personal Access Token (PAT)](https://github.com/settings/tokens) before running since this script uses the GitHub Rest API. To set this up. First, create an `.env` file with `GITHUB_TOKEN=your-github-pat-token`. Then run the sample script with:

```bash
uv run --env-file .env sample
```
