#!/usr/bin/env python3
"""Accelerator bootstrapper — clone this template into a new, ready-to-run app.

Usage:
    python bootstrap.py --name payment-insights
    python bootstrap.py --name payment-insights --dest ../payment-insights \
        --title "Payment Insights" --desc "Real-time payment analytics agent" \
        --backend-port 8010 --frontend-port 3010

What it does:
    1. Copies the template tree into --dest (excluding git/venv/node_modules and
       the bootstrapper machinery).
    2. Replaces every __PLACEHOLDER__ token across the copied text files.
    3. Writes a fresh app README.md.
    4. Optionally `git init` + commit (+ push to --remote).

Placeholders (see template.config.json):
    __APP_NAME__     kebab-case app + resource name       e.g. payment-insights
    __APP_SLUG__     snake_case (python/db identifiers)   e.g. payment_insights
    __APP_TITLE__    Human Title                          e.g. Payment Insights
    __APP_DESC__     one-line description
    __BACKEND_PORT__ FastAPI port (default 8000)
    __FRONTEND_PORT__ Vite dev port (default 3000)
    __NAMESPACE__    Temporal namespace (default = app name)
    __TASK_QUEUE__   Temporal task queue (default = <name>-agents)
    __DB_NAME__      Postgres database name (default = slug)
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parent

# Names never copied into a generated project.
EXCLUDE_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "__pycache__",
                ".pytest_cache", ".mypy_cache", ".ruff_cache", ".vite"}
EXCLUDE_FILES = {"bootstrap.py", "bootstrap.sh", "template.config.json",
                 "README.md", "BOOTSTRAP_GUIDE.md", ".DS_Store"}
# Extensions treated as binary (copied byte-for-byte, never token-replaced).
BINARY_EXT = {".crt", ".pem", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
              ".woff", ".woff2", ".ttf", ".otf", ".zip", ".gz"}

NAME_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")


def derive(args: argparse.Namespace) -> dict[str, str]:
    name = args.name
    slug = name.replace("-", "_")
    title = args.title or " ".join(w.capitalize() for w in name.split("-"))
    return {
        "__APP_NAME__": name,
        "__APP_SLUG__": slug,
        "__APP_TITLE__": title,
        "__APP_DESC__": args.desc or f"{title} — an AI agent application on the ZenLabs Agent Foundry.",
        "__BACKEND_PORT__": str(args.backend_port),
        "__FRONTEND_PORT__": str(args.frontend_port),
        "__NAMESPACE__": args.namespace or name,
        "__TASK_QUEUE__": args.task_queue or f"{name}-agents",
        "__DB_NAME__": args.db_name or slug,
    }


def is_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXT:
        return True
    try:
        with path.open("rb") as fh:
            return b"\0" in fh.read(4096)
    except OSError:
        return True


def copy_tree(dest: Path) -> None:
    for src in TEMPLATE_ROOT.rglob("*"):
        rel = src.relative_to(TEMPLATE_ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if src.is_dir():
            continue
        if len(rel.parts) == 1 and rel.name in EXCLUDE_FILES:
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def apply_replacements(dest: Path, repl: dict[str, str]) -> int:
    changed = 0
    for path in dest.rglob("*"):
        if not path.is_file() or is_binary(path):
            continue
        text = path.read_text(encoding="utf-8")
        new = text
        for token, value in repl.items():
            new = new.replace(token, value)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
    return changed


APP_README = """# {title}

{desc}

Generated from the **accelerator-bootstrapper-template** (ZenLabs Agent Foundry).

## Architecture
FastAPI + LangGraph (supervisor loop) + Temporal (durable workflows) + Redis +
Postgres + Arize Phoenix observability, with a React/Vite/Tailwind UI served by
nginx. Everything deploys to Azure Container Apps.

## Run locally
```bash
cd app
cp .env.example .env            # fill in Azure OpenAI creds
docker compose -f ../docker-compose.local.yml up -d   # postgres + redis
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
alembic upgrade head
uvicorn api.main:app --reload --port {port}      # API
python -m workers.worker                          # Temporal worker (separate shell)

cd ui && npm install && npm run dev               # UI on :{fport}
```
Or bring up the full stack (API, worker, Temporal, Phoenix):
```bash
cd app && docker compose up --build
```

## Deploy to Azure Container Apps
```bash
bash infra/aca-setup.sh          # one-time provisioning (edit VARIABLES first)
```
Or push to `main` and let `azure-pipelines-be.yml` / `azure-pipelines-fe.yml` deploy.

## Layout
```
app/
  api/         FastAPI app, routers, schemas
  agents/      LangGraph nodes, tools, state, guardrails
  workflows/   Temporal workflows + activities
  workers/     Temporal worker entrypoint
  config/      YAML prompts, rules, temporal dynamic-config
  db/          SQLAlchemy models + async engine (+ alembic/)
  observability/  OTel + Phoenix tracing
  security/    Key Vault + auth
  shared/      config, llm, logger, prompt loader
  ui/          React + Vite + Tailwind + nginx
infra/         aca-setup.sh
```
"""


def write_app_readme(dest: Path, repl: dict[str, str]) -> None:
    content = APP_README.format(
        title=repl["__APP_TITLE__"],
        desc=repl["__APP_DESC__"],
        port=repl["__BACKEND_PORT__"],
        fport=repl["__FRONTEND_PORT__"],
    )
    (dest / "README.md").write_text(content, encoding="utf-8")


def git_init(dest: Path, remote: str | None) -> None:
    def run(*cmd: str) -> None:
        subprocess.run(cmd, cwd=dest, check=True)

    run("git", "init", "-b", "main")
    run("git", "add", "-A")
    run("git", "commit", "-m", "chore: bootstrap from accelerator-bootstrapper-template")
    if remote:
        run("git", "remote", "add", "origin", remote)
        print(f"\nRemote 'origin' set to {remote}. Push with:\n  git -C {dest} push -u origin main")


def main() -> int:
    p = argparse.ArgumentParser(description="Bootstrap a new app from the accelerator template.")
    p.add_argument("--name", required=True, help="kebab-case app name, e.g. payment-insights")
    p.add_argument("--dest", help="destination dir (default: ../<name> next to the template)")
    p.add_argument("--title", help="Human title (default: derived from name)")
    p.add_argument("--desc", help="One-line description")
    p.add_argument("--backend-port", type=int, default=8000)
    p.add_argument("--frontend-port", type=int, default=3000)
    p.add_argument("--namespace", help="Temporal namespace (default: app name)")
    p.add_argument("--task-queue", help="Temporal task queue (default: <name>-agents)")
    p.add_argument("--db-name", help="Postgres DB name (default: snake_case name)")
    p.add_argument("--git-init", action="store_true", help="git init + initial commit")
    p.add_argument("--remote", help="git remote URL (implies --git-init)")
    p.add_argument("--force", action="store_true", help="overwrite dest if it exists")
    args = p.parse_args()

    if not NAME_RE.match(args.name):
        print(f"error: --name '{args.name}' must be kebab-case (a-z, 0-9, hyphens).", file=sys.stderr)
        return 2

    dest = Path(args.dest).resolve() if args.dest else (TEMPLATE_ROOT.parent / args.name).resolve()
    if dest.exists():
        if not args.force:
            print(f"error: {dest} already exists (use --force to overwrite).", file=sys.stderr)
            return 2
        shutil.rmtree(dest)

    repl = derive(args)
    print(f"Bootstrapping '{args.name}' -> {dest}")
    for k, v in repl.items():
        print(f"  {k:<18} {v}")

    copy_tree(dest)
    n = apply_replacements(dest, repl)
    write_app_readme(dest, repl)
    print(f"\nCopied template and replaced tokens in {n} files.")

    if args.git_init or args.remote:
        git_init(dest, args.remote)

    print("\nNext:")
    print(f"  cd {dest}/app && cp .env.example .env  # add Azure OpenAI creds")
    print("  docker compose -f ../docker-compose.local.yml up -d")
    print(f"  pip install -r requirements.txt && alembic upgrade head")
    print(f"  uvicorn api.main:app --reload --port {repl['__BACKEND_PORT__']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
