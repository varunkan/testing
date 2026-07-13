"""Build-time helper for Vercel: inject the Cloud Run API URL into config.js."""
from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    web_dir = Path(__file__).resolve().parents[1] / "wealthsimple_agent" / "web"
    config_path = web_dir / "config.js"

    api_url = os.environ.get("WS_AGENT_API_BASE_URL", "").strip().rstrip("/")

    lines = [
        "// API base URL for the Forge Desk frontend.",
        "// Injected at build time by Vercel / prepare_web.py.",
    ]
    if api_url:
        lines.append(f'window.API_BASE_URL = "{api_url}";')
    else:
        lines.append('window.API_BASE_URL = window.API_BASE_URL || "";')
    lines.append("")

    config_path.write_text("\n".join(lines))
    print(f"Prepared {config_path} with API_BASE_URL={api_url or '<empty>'}")


if __name__ == "__main__":
    main()
