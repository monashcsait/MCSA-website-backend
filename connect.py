"""Configure both repository folders once; no password or GitHub token is needed."""

from pathlib import Path
from urllib.parse import urlsplit
import argparse
import json

ROOT = Path(__file__).resolve().parent


def address(value, *, backend=False):
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme not in {"https", "http"} or not parsed.hostname
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or "\\" in value or any(c.isspace() for c in value)):
        raise ValueError("请输入完整网址，不要包含密码、查询参数或空格。")
    _ = parsed.port
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("线上网址必须使用 https://；本地测试可使用 http://。")
    if backend and parsed.path:
        raise ValueError("后台填域名根地址，不要加 /api 或 /admin.html。")
    if not backend and parsed.path.endswith(".html"):
        raise ValueError("官网填网站根地址，不要加 index.html。")
    return value


def main():
    parser = argparse.ArgumentParser(description="连接 MCSA 官网和后台仓库")
    parser.add_argument("--frontend", help="例如 https://ACCOUNT.github.io/mcsa-frontend/")
    parser.add_argument("--backend", help="例如 https://admin.example.org")
    args = parser.parse_args()
    try:
        frontend = address(args.frontend or input("官网完整网址（包含仓库路径）：")) + "/"
        backend = address(args.backend or input("后台域名（不包含 /api 或 /admin.html）："), backend=True)
    except ValueError as error:
        raise SystemExit(str(error))
    frontend_path = ROOT / "mcsa-frontend/assets/config.js"
    backend_path = ROOT / "mcsa-backend/deployment.json"
    frontend_path.write_text(
        "// Published content is loaded from this service on every visit.\n"
        + "window.MCSA_CONFIG = " + json.dumps({"apiBase": backend + "/api"}, indent=2) + ";\n",
        encoding="utf-8",
    )
    backend_path.write_text(json.dumps({"frontendUrl": frontend, "backendUrl": backend}, indent=2) + "\n", encoding="utf-8")
    print("配置完成：")
    print("  官网：" + frontend)
    print("  后台：" + backend + "/admin.html")
    print("  公开内容：" + backend + "/api/site")
    print("将两个文件夹的内容分别提交到对应仓库，并重启后台服务。")
    print("以后修改并发布内容，无需重新上传官网。")


if __name__ == "__main__":
    main()
