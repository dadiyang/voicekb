#!/bin/bash
cd "$(dirname "$0")/.."

export PYTHONPATH="$(pwd)/src:$PYTHONPATH"
source venv/bin/activate 2>/dev/null

exec python -m uvicorn voicekb.api.app:app --host 127.0.0.1 --port 18089 --workers 1 --log-level info
