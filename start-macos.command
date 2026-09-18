#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -f .venv/bin/python ]; then python3 -m venv .venv; fi
if ! .venv/bin/python -c 'import flask,waitress,PIL,opencc' 2>/dev/null; then .venv/bin/python -m pip install -r requirements.txt; fi
.venv/bin/python start.py
