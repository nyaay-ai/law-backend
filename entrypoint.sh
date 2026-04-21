#!/bin/bash
set -e

if [ "$RUN_MODE" = "worker" ]; then
    echo "Starting RQ worker..."
    exec rq worker --with-scheduler default --url redis://:meraredis@redis:6379/0
else
    echo "Starting Lawyer AI API..."
    exec uvicorn main:app --host 0.0.0.0 --port 8100 --reload
fi