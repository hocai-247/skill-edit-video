#!/bin/bash
# Start the app and open it in the browser.
cd "$(dirname "$0")"
PORT="${PORT:-8765}"
(sleep 1.5 && open "http://127.0.0.1:$PORT") &
exec .venv/bin/python app.py
