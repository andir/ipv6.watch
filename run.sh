#!/usr/bin/env sh

test -d .venv || python3 -m venv .venv
. .venv/bin/activate

pip install --upgrade -r requirements.txt

python3 generate.py -m dist
