# Assistant

A practical command-line AI assistant with an OpenAI-compatible chat API,
persistent local memory, and 64 tools for files, system administration,
networking, programming, databases, containers, research, and optional device
integrations.

## Requirements

- Python 3.10 or newer
- An OpenAI-compatible API key for chat requests

## Install

```bash
git clone https://github.com/beamingjunkie-lang/assistant.git
cd assistant
python -m pip install .
```

For local development, install the runtime dependency and run tests directly:

```bash
python -m pip install -r requirements.txt
python -m unittest -v
```

## Configure

Create a configuration file without overwriting an existing one:

```bash
assistant --init-config
```

Set credentials through your shell; `.env.example` documents the supported
variables, but is not loaded automatically:

```bash
export OPENAI_API_KEY="your-api-key"
export ASSISTANT_MODEL="gpt-4o"
```

The default configuration and memory paths are `~/.assistant/config.json` and
`~/.assistant/memory.json`. Use `--config PATH` or `ASSISTANT_CONFIG` to use a
different configuration file.

## Use

Start an interactive session:

```bash
assistant
```

Send a single prompt:

```bash
assistant --message "Explain this repository"
```

Discover commands and tools:

```bash
assistant --help
assistant --list-tools
assistant --list-tools cloud
assistant --show-config
```

Interactive commands:

| Command | Purpose |
| --- | --- |
| `/help` | List interactive commands |
| `/tools [category]` | List available tools, optionally filtered by category |
| `/memory` | Show local memory statistics |
| `/recall QUERY` | Search saved memory |
| `/remember TEXT` | Save a memory item |
| `/clear` | Clear the current conversation |
| `/config` | Display effective configuration with the API key redacted |
| `/status` | Display model, approval, conversation, and memory status |
| `/approval [on\|off]` | Show or change approval prompts for the current session |

## Safety

Approval prompts are enabled by default for destructive actions. Use
`--no-approval` only in an explicitly trusted environment. The assistant also
asks for scope before broad deletion, blocks filesystem-root deletion and
private-key exposure, and follows diagnostic playbooks before changing code or
system state.

Non-interactive commands use explicit exit codes: `0` for success, `1` for an
API failure, and `2` for invalid arguments, unavailable configuration, or an
unknown tool category.

## Optional integrations

| Integration | Setup | Capability |
| --- | --- | --- |
| Cloud CLI | Install AWS CLI, Azure CLI, or Google Cloud CLI | Detect installed clients and versions |
| Virtual machines | Install libvirt or VirtualBox | List local virtual machines |
| Email | No external setup | Draft RFC 5322 messages and categorize content locally |
| Android | Install Android Debug Bridge (`adb`) | List connected devices |
| Home Assistant | Set `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN` | Read states; approved service calls |

## Development

CI runs the test suite on Python 3.10 through 3.13 for pull requests and
pushes to `main`. The project is MIT licensed; see [LICENSE](LICENSE).

## Change publishing

[`AGENTS.md`](AGENTS.md) defines the required ordered workflow for generated
code: work in this checkout, validate each coherent change, commit it, and push
it directly to `main`. The GitHub repository is the authoritative source; do
not maintain a separate generated copy.

## GitHub authentication

Use GitHub CLI browser authentication for future pushes:

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

Never place API keys, personal access tokens, or private keys in repository
files or chat messages.
