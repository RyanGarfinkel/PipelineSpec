# PipelineSpec

## Dependencies

- [Act](https://nektosact.com/installation/index.html): Runs GitHub Actions jobs and workflows locally.
- [Docker](https://www.docker.com/): Needed by act. Also for mitmproxy to trace network calls.

## Sampling

The following command fetches `n` public GitHub repositories with at least one workflow file. You can set the number of samples to get by adding a `-n` flag (default 10), and use verbose logging by including the `-v` flag (default false). The resulting `samples.json` file will be stored in a `data/` directory created in the current working directory by default, but can be specified with the `-o` flag.

```bash
uv run sample
```

It is recommended to setup a GitHub [Personal Access Token (PAT)](https://github.com/settings/personal-access-tokens) before running since this script uses the GitHub Rest API. To set this up. First, create an `.env` file with `GITHUB_TOKEN=your-github-pat-token`. Then run the sample script with:

```bash
uv run --env-file .env sample
```

## PipelineSpec Tool

### Setting up environment

It is reccomended that you setup an environment file `.env` when using the PipelineSpec.

1. Generate a [mitmproxy certificate](https://docs.mitmproxy.org/stable/concepts/certificates/). This is to support network tracing and create a directory in `~/.mitmproxy`. Either pass this path into PipelineSpec using the `-C` flag or set `CERTIFICATE` in your environment variables before running.   
2.

### How to Run

The following commmand runs PipelineSpec. You must secify the repository using the `--repo` flag.

```bash
uv run --env-file .env pipelinespec --repo path-to-repository
```
