#!/bin/bash
# evo16-web.sh — Startup script for EVO 16 Web Server (launchd compatible)
cd /Users/djenttleman/dev/evo16-web
export PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/bin:/bin"
exec /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 backend/main.py
