#! /bin/bash

set -e

pip-compile $* -o test_requirements.txt requirements.in test_requirements.in
cp test_requirements.txt requirements.txt
pip-compile -o requirements.txt requirements.in
