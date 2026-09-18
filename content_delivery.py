"""Public content and the two deployment addresses, separate from CMS editing."""

from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
import json
import os


def web_address(value, *, origin_only=False):
    value = str(value).strip()
    parts = urlsplit(value)
    if (
        parts.scheme not in {"https", "http"}
        or not parts.hostname
        or parts.username or parts.password
        or parts.query or parts.fragment
        or any(c.isspace() for c in value)
        or "\\" in value
        or (origin_only and parts.path not in {"", "/"})
    ):
        raise ValueError("Use a complete http(s) address without credentials, query or fragment.")
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Public deployment addresses must use HTTPS.")
    return value.rstrip("/")


def deployment_settings(root):
    path = Path(root) / "deployment.json"
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    frontend = web_address(os.environ.get("MCSA_FRONTEND_URL", values.get("frontendUrl", "http://127.0.0.1:8080")))
    backend = web_address(os.environ.get("MCSA_PUBLIC_URL", values.get("backendUrl", "http://127.0.0.1:8000")), origin_only=True)
    parts = urlsplit(frontend)
    origins = {f"{parts.scheme}://{parts.netloc}"}
    for extra in os.environ.get("MCSA_ALLOWED_ORIGINS", "").split(","):
        if extra.strip():
            origins.add(web_address(extra, origin_only=True))
    return frontend + "/", backend, origins


def published_content(content, backend_url):
    """Never publish draft posts; make CMS-owned image paths work across domains."""
    result = deepcopy(content)
    result["posts"] = [post for post in result["posts"] if post.get("published") is True]

    def resolve(value, key=""):
        if isinstance(value, dict):
            return {name: resolve(child, name) for name, child in value.items()}
        if isinstance(value, list):
            return [resolve(child, key) for child in value]
        if (
            key in {"image", "logo", "heroLogo", "opening", "url"}
            and isinstance(value, str)
            and value.startswith(("images/", "media/"))
        ):
            return backend_url + "/" + value
        return value

    return resolve(result)
