#!/bin/bash
set -e
cd /home/irons/voicekb
source venv/bin/activate
export PYTHONPATH="/home/irons/voicekb/src:$PYTHONPATH"
mkdir -p data/{uploads,transcripts,chroma,logs}
exec python -m uvicorn voicekb.api.app:app \
  --host 0.0.0.0 \
  --port "${VOICEKB_PORT:-8088}" \
  --workers 1 \
  --log-level info
