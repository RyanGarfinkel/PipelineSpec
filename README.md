# PipelineSpec

## Dependencies

- [Act](https://nektosact.com/installation/index.html): Runs GitHub Actions jobs and workflows locally.
- [uv](https://docs.astral.sh/uv/): Python package manager.
- [Docker](https://www.docker.com/): Runs act and the privileged tracing sidecar.
- [mitmproxy](https://mitmproxy.org/): Traces and mocks network calls from inside the sidecar.

## How to Use

Create a `.env` file in the root of this repository:

```bash
CERTIFICATE=~/.mitmproxy
OPENAI_API_KEY=your-api-key
```

You must run `docker build` first. Then you can run the PipelineSpec tool.

```bash
docker build -t pipeline-sidecar:latest src/pipelinespec/docker
uv run --env-file .env pipelinespec -r data/repositories/toy -m gpt-6-luna
```

## Experiment

### Generate Samples

Finds public GitHub repositories and writes `data/manifest.json`. Add `GITHUB_TOKEN=your-github-pat-token` to `.env` to avoid rate limit.

```bash
uv run --env-file .env sample -n 10 -t 4
```

### Run the Experiment

Runs PipelineSpec on data in `data/manifest.json` and writes each one's results to `data/results/<model>/<repo>/`. Can use `--constraints-only` or `--trace-only` to seperate stages. `-k` can be used with constraints only to rerun constrant agent multiple times.

```bash
uv run --env-file .env experiment -n 10 -t 2 -m gpt-6-luna
```
