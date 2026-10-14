#!/usr/bin/env bash
# build.sh — Render build script for PGDesk
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate
python manage.py seed_demo
