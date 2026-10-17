import os
from pathlib import Path

import yaml
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

BASE = Path(__file__).resolve().parent

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Assigned OS-level env vars. setdefault keeps any value already set on the
# hosting platform, and fills in the assigned value if you forgot to set it.
os.environ.setdefault("APP_PORT", "8970")
os.environ.setdefault("APP_LOG_LEVEL", "warning")

# Layer 1: hardcoded defaults
DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

ALIASES = {"NUM_WORKERS": "workers"}
PREFIX = "APP_"
IGNORED = {"env"}  # APP_ENV selects the YAML file; it is not a config key


def coerce(key, value):
    if key in ("port", "workers"):
        return int(str(value).strip())
    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return str(value)


def env_key(name):
    """Map an env-style variable name to a config key, or None to skip it."""
    if name in ALIASES:
        return ALIASES[name]
    if name.startswith(PREFIX):
        key = name[len(PREFIX):].lower()
        return None if key in IGNORED else key
    return None


def load_yaml(env):
    path = BASE / f"config.{env}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def load_dotenv_file():
    path = BASE / ".env"
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        key = env_key(name)
        if key:
            out[key] = value
    return out


def load_os_env():
    out = {}
    for name, value in os.environ.items():
        if name.startswith(PREFIX):
            key = env_key(name)
            if key:
                out[key] = value
    return out


@app.get("/effective-config")
def effective_config(set: list[str] = Query(default=[])):
    env = os.environ.get("APP_ENV", "development")
    config = dict(DEFAULTS)                # 1. defaults
    config.update(load_yaml(env))          # 2. config.<env>.yaml
    config.update(load_dotenv_file())      # 3. .env
    config.update(load_os_env())           # 4. OS env (APP_*)
    for item in set:                       # 5. CLI overrides via ?set=key=value
        if "=" in item:
            key, value = item.split("=", 1)
            key = key.strip()
            config[ALIASES.get(key, key.lower())] = value

    result = {key: coerce(key, value) for key, value in config.items()}
    result["api_key"] = "****"
    return result


@app.get("/")
def root():
    return {"status": "ok", "endpoint": "/effective-config"}
