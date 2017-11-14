#! /bin/bash
tox

# For a specific test ( defaults to run in all python versions):
# tox -- tests.tests:TestZappa.test_lets_encrypt_sanity -s

# For a specific test run with a specific python version (p27, py36):
# tox -e py27 -- tests.tests:TestZappa.test_lets_encrypt_sanity -s
