from __future__ import annotations

from pathlib import Path


def load_project_env(project_root: Path | None = None) -> bool:
    """Load `.env` from project root if present. Does not override existing env vars."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False

    root = project_root or Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if not env_path.is_file():
        return False
    load_dotenv(env_path, override=False)
    return True
