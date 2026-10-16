"""Shared local configuration. Never put credentials in URLs or preference snapshots."""
import os
import secrets
from pathlib import Path

VERSION = "2.0.0"
PROTOCOL_REVISION = "evo16-2026-10-16"
DATA_DIR = Path(os.environ.get("EVO16_DATA_DIR", Path.home() / "Library/Application Support/EVO16Remote"))
TOKEN_FILE = DATA_DIR / "api-token"


def api_token() -> str:
    override = os.environ.get("EVO16_API_TOKEN")
    if override:
        return override
    DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    DATA_DIR.chmod(0o700)
    try:
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        TOKEN_FILE.chmod(0o600)
    else:
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(32))
    value = TOKEN_FILE.read_text().strip()
    if len(value) < 32:
        raise RuntimeError("Credencial API inválida; revisar api-token en la carpeta de datos")
    return value
