"""DSH profile configuration for the search CLI and optional relevance gate."""

import json
import os
import stat
from pathlib import Path


class ConfigError(ValueError):
    """Only static, non-sensitive reason codes belong in this exception."""


def credential_path() -> Path:
    override = os.environ.get("SEARCH_LAYER_CREDENTIALS")
    if override:
        path = Path(override).expanduser()
    elif home := os.environ.get("DSH_HOME"):
        path = Path(home).expanduser() / "credentials/search.json"
    else:
        # An installed skill can be run by absolute path outside a DSH shell.
        skills = Path(__file__).resolve().parents[2]
        root = skills.parent if skills.name == "skills" else Path.home() / ".dsh"
        path = root / "credentials/search.json"
    if not path.is_absolute():
        raise ConfigError("profile_or_override_path_must_be_absolute")
    return path


def load_credentials() -> dict:
    path = credential_path()
    try:
        # Non-blocking open lets fstat reject a FIFO without hanging a DSH tool call.
        opener = lambda name, flags: os.open(name, flags | getattr(os, "O_NONBLOCK", 0))
        with open(path, encoding="utf-8", opener=opener) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ConfigError("credentials_not_regular_file")
            if os.name == "posix" and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
                raise ConfigError("credentials_require_private_owner_access")
            data = json.load(stream)
    except FileNotFoundError:
        if os.environ.get("SEARCH_LAYER_CREDENTIALS"):
            raise ConfigError("explicit_credentials_file_missing") from None
        return {}  # Environment-only profiles are supported.
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ConfigError("credentials_unreadable_or_invalid_json") from None
    if not isinstance(data, dict):
        raise ConfigError("credentials_must_be_object")
    return data


def get_keys() -> dict:
    """One trusted file; per-provider environment settings override its fields."""
    data = load_credentials()
    out = {}
    for provider in ("exa", "tavily"):
        section = data.get(provider)
        if isinstance(section, str) and section:
            out[provider] = section
        elif isinstance(section, dict):
            if key := section.get("apiKey"):
                out[provider] = key
            if url := section.get("apiUrl") or section.get("baseUrl") or section.get("apiBase"):
                out[provider + "_url"] = url
        if url := next((data[provider + s] for s in ("ApiUrl", "ApiBase", "BaseUrl") if data.get(provider + s)), None):
            out[provider + "_url"] = url
        prefix = provider.upper()
        if key := os.environ.get(prefix + "_API_KEY"):
            out[provider] = key
        if url := os.environ.get(prefix + "_API_BASE") or os.environ.get(prefix + "_API_URL"):
            out[provider + "_url"] = url

    # Do not synthesize defaults here: providers.grok.config_from_keys owns them.
    fields = {
        "apiKey": "key", "apiUrl": "url", "model": "model", "transport": "transport",
        "searchModel": "search_model", "chatModel": "chat_model",
        "fallbackSearchModels": "fallback_search_models", "reasoningEffort": "reasoning_effort",
        "reasoningFormat": "reasoning_format", "webSearch": "web_search", "xSearch": "x_search",
        "stream": "stream", "structuredOutput": "structured_output", "timeoutSeconds": "timeout_seconds",
        "modelDiscovery": "model_discovery", "modelCacheTtlSeconds": "model_cache_ttl_seconds",
        "fallbackPolicy": "fallback_policy",
    }
    section = data.get("grok")
    if isinstance(section, dict):
        out.update({"grok_" + name: section[k] for k, name in fields.items() if k in section})
    if model := os.environ.get("GROK_MODEL"):
        out["grok_chat_model"] = model
    for name in fields.values():
        env = {"key": "GROK_API_KEY", "url": "GROK_API_URL"}.get(name, "GROK_" + name.upper())
        if value := os.environ.get(env):
            out["grok_" + name] = value
    return out
