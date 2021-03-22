#! /bin/bash

set -e

ARGS=""
if [ "$1" == "--upgrade" ]; then
    ARGS="-U"
fi

pip install -U pip-tools
pip-compile ${ARGS} -o test_requirements.txt requirements.in test_requirements.in
cp test_requirements.txt requirements.txt
pip-compile -o requirements.txt requirements.in
