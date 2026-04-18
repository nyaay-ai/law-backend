#!/bin/bash
set -e

echo "Starting Lawyer AI API..."
exec uvicorn main:app --host 0.0.0.0 --port 8100 --reload
