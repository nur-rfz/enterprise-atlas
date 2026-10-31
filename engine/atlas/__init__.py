"""Enterprise Atlas engine."""
import os
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader (repo root), so keys never need to be exported by hand."""
    for p in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if p.is_file():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break


_load_dotenv()
