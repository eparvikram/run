#!/bin/bash
# For development with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# For production, consider Gunicorn with Uvicorn workers:
# gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000