# Assistant

A Python CLI assistant with an OpenAI-compatible tool-calling loop, persistent
memory, and tools for files, system administration, networking, programming,
databases, containers, and research.

## Requirements

- Python 3.10 or newer
- An OpenAI-compatible API key for chat usage

## Install and run

```bash
python -m pip install -r requirements.txt
export OPENAI_API_KEY="your-api-key"
python main.py
```

Run a single prompt:

```bash
python main.py --message "Explain this repository"
```

## Development

Run the test suite:

```bash
python -m unittest -v
```

Continuous integration runs this suite on Python 3.10 through 3.13 for pushes
to `main` and pull requests.

## Operational safeguards

The assistant asks for a specific performance target before optimizing, asks for
deletion scope before removing broad sets of files, blocks filesystem-root
deletion and private-key exposure, and uses diagnostic playbooks for repository
investigation, build failures, Git recovery, Docker, networking, deployments,
and upgrades.

## GitHub authentication

Use GitHub CLI browser authentication for future pushes:

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

Never place API keys, personal access tokens, or private keys in repository
files or chat messages.
