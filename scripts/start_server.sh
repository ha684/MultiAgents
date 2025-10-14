#!bin/sh
#Data migration
alembic upgrade head
echo "Starting API server..."
#Start api server
uv run -m src.main
