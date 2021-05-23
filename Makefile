
help:
	@echo 'Zappa Make Targets'
	@echo '-----------------------'
	@echo 'These targets are aimed at making development, testing, and building easier'
	@echo ''
	@echo 'Setup'
	@echo 'make clean: Remove the built files, local caches, mypy and coverage information'
	@echo 'make requirements: Generate requirements from requirements.in and install them to the current environment'
	@echo 'make build: Build the source and wheel'
	@echo ''
	@echo 'Linting'
	@echo 'make flake: Flake8 checking'
	@echo 'make mypy: Run static type checking for zappa and tests directories'
	@echo 'make isort: Sort imports'
	@echo 'make black: Format project code according to Black convention'
	@echo ''
	@echo 'Testing'
	@echo 'make tests: Run all project tests. Additional make targets exist for subsets of the tests. Inspect the Makefile for details'

.PHONY: clean requirements build flake mypy isort black tests

clean:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	rm -rf .mypy_cache dist build *.egg-info
	rm -f .coverage

requirements:
	./requirements.sh
	pip install -r requirements.txt
	pip install -r test_requirements.txt

build: clean requirements-install
	python setup.py sdist
	python setup.py bdist_wheel 

mypy:
	mypy --show-error-codes --pretty --ignore-missing-imports --strict zappa tests

black:
	black zappa tests

black-check:
	black zappa tests --check
	@echo "If this fails, simply run: make black"

isort:
	isort --recursive . 

flake:
	flake8 zappa --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 zappa --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

test-docs:
	nosetests tests/tests_docs.py --with-coverage --cover-package=zappa --with-timer

test-handler:
	nosetests tests/test_handler.py --with-coverage --cover-package=zappa --with-timer

test-middleware:
	nosetests tests/tests_middleware.py --with-coverage --cover-package=zappa --with-timer

test-placebo:
	nosetests tests/tests_placebo.py --with-coverage --cover-package=zappa --with-timer

test-async:
	nosetests tests/tests_async.py --with-coverage --cover-package=zappa --with-timer

test-general:
	nosetests tests/tests.py --with-coverage --cover-package=zappa --with-timer

tests: clean test-docs test-handler test-middleware test-placebo test-async test-general
