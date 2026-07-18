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

## Optional integrations

- **Cloud:** `cloud_cli_status` detects installed AWS CLI, Azure CLI, and Google
  Cloud CLI clients without accessing cloud resources.
- **Virtual machines:** `list_virtual_machines` reads local libvirt or
  VirtualBox inventory when those tools are installed.
- **Email:** `draft_email` produces a local RFC 5322 draft and
  `categorize_email` classifies message text without sending or reading mail.
- **Mobile:** `android_device_info` reads devices available through `adb`.
- **Smart home:** set `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN` in the
  environment to read Home Assistant states. Service calls require approval.

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
