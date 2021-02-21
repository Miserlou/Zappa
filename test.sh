#! /bin/bash
set -e
nosetests --with-coverage --cover-package=zappa

# For a specific test:
# nosetests tests.tests:TestZappa.test_lets_encrypt_sanity -s
