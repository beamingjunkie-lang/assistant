"""Configuration management for the assistant."""

import os
import json
import logging
import tempfile
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".assistant" / "config.json"


@dataclass
class Config:
    # LLM
    api_key: str = ""
    api_base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.2
    timeout: int = 60

    # Memory
    memory_path: str = str(Path.home() / ".assistant" / "memory.json")
    max_memory_entries: int = 1000

    # Logging
    log_level: str = "INFO"
    log_file: str = str(Path.home() / ".assistant" / "assistant.log")

    # Agent
    max_iterations: int = 10
    require_approval: bool = True
    approved_tool_categories: list = field(default_factory=lambda: [
        "system_read", "file_read", "network_read", "process_read",
        "web", "productivity", "research", "pkm",
    ])

    # Paths
    workspace: str = str(Path.home() / "assistant_workspace")

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        config_path = Path(path or os.environ.get("ASSISTANT_CONFIG", DEFAULT_CONFIG_PATH))
        cfg = cls()

        if config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
                logger.debug("Loaded config from %s", config_path)
            except Exception as e:
                logger.warning("Failed to load config from %s: %s", config_path, e)

        # Environment overrides
        if api_key := os.environ.get("OPENAI_API_KEY") or os.environ.get("ASSISTANT_API_KEY"):
            cfg.api_key = api_key
        if base := os.environ.get("ASSISTANT_API_BASE"):
            cfg.api_base_url = base
        if model := os.environ.get("ASSISTANT_MODEL"):
            cfg.model = model
        if level := os.environ.get("ASSISTANT_LOG_LEVEL"):
            cfg.log_level = level

        return cfg

    def save(self, path: Optional[Path] = None) -> None:
        config_path = Path(path or os.environ.get("ASSISTANT_CONFIG", DEFAULT_CONFIG_PATH))
        config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=config_path.parent,
                delete=False,
            ) as temporary_file:
                json.dump(asdict(self), temporary_file, indent=2)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_path = Path(temporary_file.name)
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, config_path)
        except OSError:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
        logger.debug("Saved config to %s", config_path)

    def setup_logging(self) -> None:
        log_path = Path(self.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        level = getattr(logging, self.log_level.upper(), logging.INFO)
        handlers = [logging.StreamHandler()]
        try:
            handlers.append(logging.FileHandler(log_path))
        except Exception:
            pass
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=handlers,
        )
