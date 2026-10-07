"""Optional `kinloom.json` next to the game. Nothing is required: keys come from the environment, the model is detected.

    {
      "provider": "deepseek" | "anthropic" | "openai" | "ollama" | "custom" | "offline"     (an API key)
                | "claude-code" | "codex" | "gemini-cli" | "opencode" | "command",        (a coding agent's subscription)
      "model": "...", "base_url": "...", "command": ["program", "arg", ...] (provider "command"),
      "tools": {"open_door": {"door": "north"}, ...},   (the game's tools: characters use them by name)
      "language": "English", "calls_per_minute": 30,
      "prices": {"input": 0.3, "cached_input": 0.006, "output": 1.2, "source": "provider page, read on <date>"},
      "memory": ".kinloom/memory.json", "port": 7717,
      "banned_words": ["..."],     (model text containing one of them is never shown: the offline answer is used)
      "max_cost_per_hour": 1.0, "max_cost_per_day": 10.0,   (dollars; need "prices")
      "reply_timeout": 8,          (seconds a spoken reply may take on a hosted model before the offline reply)
      "lore": ["The village is Ashford.", ...],              (world facts every character treats as true)
      "characters": {"Mira": {"soul": "one sentence", "offline": "Busy.", "tools": {"give": {"item": "sword"}},
                              "trust": {"give": 0.3}, "invent": false, "language": "French",
                              "warmth": 0.4, "secret_trust": 0.6, "warm_up": 0.3, ...}}
    }
Characters and lore here need no code in the game (every engine, every session); edits are picked up while it runs.
Keys are never read from this file: DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY or KINLOOM_API_KEY.
"""
import json
import os

from . import harness as _harness

from .providers import ANTHROPIC_MODEL, ANTHROPIC_URL, DEEPSEEK_MODEL, DEEPSEEK_URL, OLLAMA_URL, Anthropic, OpenAICompatible, _ollama_model, detect

FILE = "kinloom.json"
DEFAULTS = {"language": "English", "calls_per_minute": 30, "memory": os.path.join(".kinloom", "memory.json"), "port": 7717}


class ConfigError(Exception):
    pass


def load(folder="."):
    path = os.path.join(folder, FILE)
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise ConfigError("%s is not valid JSON: %s" % (path, e))
        if not isinstance(data, dict):
            raise ConfigError("%s must be a JSON object" % path)
        for secret in ("key", "api_key", "apiKey", "token"):
            if secret in data:
                raise ConfigError("%s contains '%s': keys belong in environment variables, never in files" % (path, secret))
        cfg.update(data)
        cfg["_path"] = path
    return cfg


def update(folder=".", **changes):
    """Writes keys into kinloom.json (None removes one), keeping the rest; creates the file when there is none."""
    path = os.path.join(folder, FILE)
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise ConfigError("%s is not valid JSON (%s): fix it first, nothing was changed" % (path, e))
        if not isinstance(data, dict):
            raise ConfigError("%s must be a JSON object: nothing was changed" % path)
    for k, v in changes.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return path


def provider(cfg, env=None):
    """The provider the config asks for, else the one detected from the environment. None = offline."""
    env = os.environ if env is None else env
    kind = (cfg.get("provider") or "").lower()
    model = env.get("KINLOOM_MODEL") or cfg.get("model")
    if kind == "offline" or env.get("KINLOOM_OFFLINE", "").lower() in ("1", "true", "yes"):
        return None
    agent = env.get("KINLOOM_HARNESS") or (kind if kind in _harness.KINDS else None)
    if agent and not env.get("KINLOOM_SCRIPT"):         # the developer's coding agent answers (their subscription)
        # its own model setting: KINLOOM_MODEL names a model of an API (e.g. "vendor/model" on OpenRouter), which the
        # agent would not know (measured: every call failed when it was passed on)
        agent_model = env.get("KINLOOM_HARNESS_MODEL") or cfg.get("model") or None
        try:
            return _harness.Harness(agent.lower(), agent_model, cfg.get("command"), pool=cfg.get("pool"))
        except (TypeError, ValueError) as e:
            raise ConfigError("%s: %s" % ("KINLOOM_HARNESS" if env.get("KINLOOM_HARNESS") else "kinloom.json", e))
    if env.get("KINLOOM_BASE_URL") and env.get("KINLOOM_MODEL"):  # an explicit endpoint in the environment wins
        return detect(env)
    if kind == "deepseek":
        key = env.get("DEEPSEEK_API_KEY") or env.get("KINLOOM_API_KEY")
        return OpenAICompatible(cfg.get("base_url") or env.get("DEEPSEEK_BASE_URL") or DEEPSEEK_URL, key, model or DEEPSEEK_MODEL, "deepseek", True) if key else None
    if kind == "anthropic":
        key = env.get("ANTHROPIC_API_KEY") or env.get("KINLOOM_API_KEY")
        return Anthropic(key, model or ANTHROPIC_MODEL, cfg.get("base_url") or ANTHROPIC_URL) if key else None
    if kind == "openai":
        key = env.get("OPENAI_API_KEY") or env.get("KINLOOM_API_KEY")
        if not model:
            raise ConfigError('provider "openai" needs "model" in kinloom.json (Kinloom never guesses a model name)')
        return OpenAICompatible(cfg.get("base_url") or "https://api.openai.com/v1", key, model, "openai") if key else None
    if kind == "ollama":
        url = cfg.get("base_url") or OLLAMA_URL
        local = model or _ollama_model(url)
        return OpenAICompatible(url.rstrip("/") + "/v1", "", local, "ollama") if local else None
    if kind == "custom":
        if not cfg.get("base_url") or not model:
            raise ConfigError('provider "custom" needs "base_url" and "model" in kinloom.json')
        return OpenAICompatible(cfg["base_url"], env.get("KINLOOM_API_KEY") or "", model, "custom")
    if kind:
        raise ConfigError('unknown provider "%s" (an API key: deepseek, anthropic, openai, ollama, custom; a coding '
                          'agent: %s; or offline)' % (kind, ", ".join(_harness.KINDS)))
    if model and not env.get("KINLOOM_MODEL"):
        env = dict(env, KINLOOM_MODEL=model)
    return detect(env)
