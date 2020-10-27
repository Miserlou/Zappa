# Zappa Changelog

## 0.52.0
* Remove dateutil version restriction
* Fix failed downloads of wheel packages with non-alphanumeric characters
* Last release from Miserlou/Zappa
* Removed references to zappa.io

## 0.51.0
* Lambda Layers
* Cognito support
* Skip venv check if --no_venv argument is passed
* Fix for abi3 filename matching
* Wait for the Load Balancer to become active before proceeding
* Add option 'Scheme' for alb config
* Allow full path exclusions while packaging
* Workaround for werkzeug incompatibility
* And assorted fixes

## 0.50.0
* Updated manylinux to support manylinux1/manylinux2010/manylinux2014 packages
* Fixed issue with duplicated cookie headers in API Gateway
* Various maintenance updates to the README file
* Remove old python 2.7 code (not all yet)
* Use pip-tools to manage dependencies (and remove pinned dependencies from the package)
* Add option for concurrency limit
* Use safe_load with YAML
* Support for ABI3 binary packages (particularly cryptography)
* Remove dependency on lambda-packages

## 0.49.0
* Added support for Python 3.8
* Fixed boto3 reporting of long names
* Added support for new AWS Regions
* Minor bug and README fixes

## 0.48.2
* Last version with Python 2.7 support.
* Fix for invalid values of HTTP_HOST and others (introduced in 0.48.0)

## 0.48.1
* Fix for an issue where you couldn't update a function if it had been deployed with a version prior to 0.48.0
* Support for private (VPC-only) API Gateway endpoints

## 0.48.0
* Deprecation of zappa.async because async is a reserved word in 3.7, please use zappa.asynchronous
* Support for Application Load Balancer as an alternative to API Gateway
* Improvements in manylinux wheel downloads
* Support for multi-value query strings
* Python 3.7 support
* Support for multi-value headers
* Support for the new 256kB async limit
* Bunch of small typos, fixes and documentation improvements
* Use Django 2 on tests with python 3
* Stop applying tags on buckets not created by zappa
* Be more forgiving on 504 errors during deployment
* Fix cleanup of DynamoDB table for async tasks
* Detection of invalid bucket names
* Flake8 checks added to tests

## 0.47.1
* Handle accounts with more than 100 domains in route 53
* Force requests upgrade to 2.20.0 for compatibility with urllib3 1.24
* Allow defining API Gateway policies (including restricting access to one IP address)

## 0.47.0
* Support for SQS events
* Added test to enforce running of doctoc
* Add support for running django as a WSGI app (for NewRelic and others)
* Updates AWS regions for lambda and API Gateway
* Fix support for gcloud and other packages with slim_handler
* Add --disable-keep-open to zappa tail
* Dependency updates
* Fix pyenv invocation
* Add custom base_path stripping support
* Multiple documentation fixes and improvements
* first iteration of a documented deploy policy

## 0.46.2
* hotfix for creating virtual environments

## 0.46.1
* Hotfix for pipenv support (pip >10.0.1)
* Adds AWS GovCloud support!
* Test fix

## 0.46.0
_Okay, I dropped the ball for a long time. Bad BDFL!_
_New releases will come much faster once again_
* Pip10 compatibility
* Add support for base path configuration in API gateway custom domain.
* Fix path case sensitivity in get_installed_packages
* Move task decorator async decision from import time to call time.
* Fix documentation error in authorizer stanza of zappa_settings.json.
* Adding explicit UTF-8 encoding for Flask app detection
* Bump lambda packages version
* Fix for work with latest Werkezeug
* Fixed parameter name from 'FunctionNmae' -> 'FunctionName'
* Remove `use`; fixes #1522
* Philippe Trounev is awesome
* fix case sensitivity problem for comparing package location
* isBase64Encoded is a boolean flag instead of string true
* check pip return code as sometimes pypi lookup fails
* Add support to delete old versions of lambda functions.
* Reactor title casing of dict keys into a utility function
* Add `role_arn` settings variable
* ..and too many more, check the changelog!

## 0.45.1
* Make `package_info.json` consistent across Python versions
* Fixes to `task_sns`

## 0.45.0
* Add support for SQLite on Python 3.6 (LP bump)
* Add unique package identifier file
* Fixes #1171 don't colorize partial words
* Various small changes
* More robust OpenSSL parsing for LE
* Update applies tags
* Allows deploying and updating from existing S3 package

## 0.44.3
* Slim handler packaging hotfix - thanks @mcrowson!

## 0.44.2
* Non-Dynamo asynx hotfix - thanks @jwkvam!

## 0.44.1
* Packaging hotfix - thank Yunseop!

## 0.44.0
* Async responses (thanks Sean!)
* Remove setLevel call from common log
* Fix #1023
* Merge #1058, 1059, 1073
* Allow overriding of endpoint_url arg
* Add support for API Gateway stage variables
* Add AWS X-Ray support (thanks @mathom!)
* Events take kwargs (Thanks @mcrowson!)
* Detect P2/3 during `init`
* Include stage names in `slim_handler` zips
* Allow `-s` with `manage`
* Use same S3 bucket for global endpoints
* Fix bug with mixed-case packages
* Cache wheels, fix 0-byte wheels

## 0.43.2
* Add index prefix to each subsequent schedule expression for the same event (#1051)
* fix/Only update CORS on resources which have an OPTIONS method (#1036)
* Support for binary support and cors simultaneously (#1011)
* Set Flask script name based on domain which the request was made to (#1015)
* Fix SNS Async (#1055)
* GZip for slim handler
* Force color option
* Various dep bumps

## 0.43.1
* Fixes #1001, don't override AWS env vars if k:v not set. Thanks Nik and Sean!

## 0.43.0
* Checks for the key 'Environment' when fetching remote lambda env vars (#988)
* except BotoCoreError before general exception in zappa.cli.update
* make cookie hack case-insensitive
* Fix #998 - Make environment variable keys strings instead of byte arrays in python 3.6
* Add --disable_progress command line parameter
* #946 - Allow setting cors to false.
* #870 Lambda from outside
* Implement context header mappings - Feature Request Issue #939
* Separating out native AWS environment variables ##962
* Rule name shortening
* Splintering aws_environment_variables from environment_variables (to avoid overwriting AWS native env vars).

## 0.42.2
* Add exclude for __pycache__ contents (#943)
* Fix #937 - Use get_data
* Add support for configuring APIGW cache TTL and encryption #942
* Addressing #909: Don't load credentials for 'package' command

## 0.42.1
* Small fixes for #918, #922, #803, #802, #799, #888, #903, #893, #828, #874, and others.
* Support for manylinux wheels Python 3.6 package downloading.
* Py3 `certify` fixes.
* Add support for multiple expressions when scheduling
* Fix content-type headers not passing through on DELETE
* Avoid creating __init__.py in a directory next to a module (.py file) with the same name
* Check recursively if there is any .py{,c} file in a directory before creating __init__.py
* Fix SNS event tasks
* Bump lambda-packages

## 0.42.0
* Cached manylinux wheel installed
* New dependency installation formatting
* Clarify "stage" vs "environment" terminology in code
* Fix problem with capitalized packages
* Delete local package if using wheels version. This saves several MBs on package size in some cases (e.g. numpy).
* Thanks to @mcrowson, @nikbora and @schuyler1d

## 0.41.3
* Various Python3 fixes
* Remove some dead code
* More binary package fixes thanks to and @nikbora and @bxm156
* Improved async tasks thanks to @schuyler1d
* Various small changes

## 0.41.2
* Support for new `lambda-packages` format (Python3 support)
* Fix `setup.py` on Windows Python3
* Fix #818 - python3 import for LE
* Support AWS-specific environment variables (with KMS)

## 0.41.1
* Add `template` command
* Add `--json` in more places
* Add `--output` to package
* Support for manylinux wheels Python 3.6 package downloading #803
from nikbora
* Fix PyEnv exit code #799

## 0.41.0
* Add Python3 Support! #793, #6
* Deprecate `lets_encrypt_expression`
* Refactor a bunch of stuff to work with Python3 package restrictions >:[
* #776 fix for libmysqlclient.so.18 error when using `slim_handler`
* add profile and region detection to init - thanks @pdpol
* #774 Wsgi environment improvements (Fix untrustworthy remote_addr)
* Only create `__init__.py` file if there are python files or sub dirs in the folder
* Update docs to reflect lambda name prepended to role_name
* Guard log responses (thanks @scoates)

## 0.40.0
* Add Async Task Support! Lots of tickets and PRs related, including #61, #603, #694 and #732.
* More info here: https://blog.zappa.io/posts/zappa-introduces-seamless-asynchronous-task-execution
* Fix Django non-WSGI function initialization, #748
* Add support for AWS Lambda Dead Letter Queue, #740
* Fix API Gateway test button (the bolt button), #735
* Switch to using per-lambda-name (project-stage) rather than a single default LambdaExecutionRole

## 0.39.1
* Fix broken Let's Encrypt trying to use new ACM ARNs
* Add `apigateway_description` setting, fixes #722
* More aggressive virtualenvironment checking

## 0.39.0
* Add `certificate_arn` setting, support for AWS Certificate Manager (#710)
* Fix zip permissions when building on Windows (#714)
* Change the active working directory to `/tmp` when using the slim handler so that relative filepaths work. (#711)

## 0.38.1
* Hotfix for broken Django deploys

## 0.38.0
* Add confirm to `certify`
* Add `--manual` to `--certify`
* Fix `certify` for existing domains
* Add `extra_permissions` setting
* Add `shell` command

## 0.37.2
* Revert to Kappa 0.6.0 #684 and others
* Add binary support for more HTTP methods, #696

## 0.37.1
* Add binary upload support, fix #683

## 0.37.0
* Add support for custom, non-Let's Encrypt certificates, thanks to Benjamin Congdon
* Change default permissions to allow executable binaries, #682
* Fix binary support for Django POST, #677

## 0.36.1
* Remove Kappa 0.6 specific hack
* Bring back '-' substitution

## 0.36.0
* Add automatic support for serving binary files! Via @wobeng, closes #481
* Fixes `rollback` default back to 1 from 0, #673
* Ensure correct chmodding during package creation, #484
* Update regions that Zappa supports, #667
* Validate function names based on actual gateway rules #521
* Fix unschedule events with trimmed names #662
* Fix a few places where `extends` wasn't respecting `stage_config`, #655
* Begin to remove some dead code
* Dependency bumps

## 0.35.2
* Adds `--non-http` to `tail`

## 0.35.1
* Fix 64bit `lambda-packages` (#645)
* Fix wheel packages (#642)

## 0.35.0
* Replace ZappaCookie with Set-Cookie permutation! :D (#636)
* Bump `lambda-packages` version
* Fix installed_packages_name_set (#637)
* Add `slim_handler` (#548)
* Various small requirements bumps and other fixes.

## 0.34.0
* Adds `--since` and `--filter` to `tail`
* Fixes `unschedule` command when used with specific stage

## 0.33.0
* Adds `package` command
* Forbids the use of unicode environment variable keys
* Initialize wsgi.errors to sys.stderr (was '')
* Accept `AWS_SESSION_TOKEN` when executing via an IAM role (#589)
* Set `REMOTE_USER` even when using `iam_authorization`
* Rename `lets_encrypt_schedule` to `lets_encrypt_expression` (#571)
* Messages in `tail` are now sequential
* Bump version requirements, update README
* Various other small changes

## 0.32.1
* File `tail` broken in CLI refactor

## 0.32.0
* Add Cognito Authorizers
* Refactor CLI, add Bash Completion
* Improve manylinux wheels
* Varios fixes and req bumps

## 0.31.0
* Adds the `cors` feature, big thanks to @AusIV!
* Adds support for `-e` eggs, thanks to @schuyler1d and @xuru!
* Adds support for YAML settings files. Eat up, hipsters.

## 0.30.1
* Add `--http` filter to `tail`
* Prefer `apigateway_enabled` but still respect `use_apigateway`, #493

## 0.30.0
* Adds colors to `zappa tail` output, fixes #492
* Adds `--no-color` CLI argument
* Adds fatal warning for bad `app_function`s, fixes #485.

## 0.29.2
* Fix S3 broken S3 events
* Move `use_apigateway` to `apigateway_enabled`

## 0.29.1
* Fixes progress bar error for manylinux packages
* Safely handle freezes when downloading from PyPI
* Adds `s3://` syntax for remote env files. (#478, thanks @Leandr!)

## 0.29.0
* Adds `extends` syntax to settings file.
* Fixes Django migrations, #464
* Adds support for manylinux wheels! #398
* Fixes multiple events in `status` command
* Fixes support for `certify` on apex domains, #451

## 0.28.3
* Filter private hosted zones to avoid conflicts while certifying
* Fix small Python3 bug (#457)
* Fix for #453 (windows os.path)
* Re-raise Zappa exception with full traceback
* Skip pyc on django migrations, fixes #436
* Delete correct domain name, #448

## 0.28.2
* added region and lambda name to not deployed error

## 0.28.1
* Add "global" mode to init. Expect a blog post soon!
* Small refactors and dependency upgrades.

## 0.28.0
* `--json` for machine readable status output
* `--all` for global deployment prep
* Better exit code handling
* Get AWS region from profile if not set in zappa_settings.json
* Fix broken Django management command invocation
* Add Kinesis permission
* Add capability to specify authoriser arn
* Various refactors and small fixes

## 0.27.1

* Bump lambda-packages
* Fix new Django unicode problems (#397)
* Ensure env vars are strings via @scoates
* Fix #382

## 0.27.0

* Remove many hacks using new API Gateway features.
    * Closes #303, #363, #361
    * See the [blog post](https://blog.zappa.io/posts/unhacking-zappa-with-new-apigateway-features) for more details!
* Bump dependencies - make sure you reinstall your requirements!
* Improved stack update handling.

### 0.26.1 (Never Published)

* Warn on namespace collisions.
* Bump lambda-packages version.

## 0.26.0

* Use simplified API Gateway configuration, via @koriaf.
* Add better support for `use_apigateway` without any supplied app function. Reported by @mguidone.
* Truncate illegally long event functions names. Reported by @mguidone.

## 0.25.1

* Remove 'boto' from default excludes. #333, thanks Claude!
* Don't allow invalid API Gateway characters in the config. Thanks @scoates!
* Better respect for `use_apigateway` in `update` command.
* Avoids hang with API Gateway limit reached.
* Fix DynamoDB/Kinesis event sources, add docs. Big thanks Claude!

## 0.25.0

* Add ability to invoke raw python strings, like so:

    `zappa invoke dev "print 1+2+3" --raw`

* Fixes multi-argument `manage` commands.
* Updated related documentation.
* Fixes places where program was exiting with status 0 instead of -1. Thanks @mattc!
* Adds old-to-new-style check on delete, thanks @mathom.

## 0.24.2

* Fix a problem from trying to `update` old-style API routes using new Tropo code. Ensures `touch` works as intended again. Fix by @mathom.

## 0.24.1

* Add a helpful failure warning for users without permissions to automatically manage execution roles.
* Fix potential div by zero error in new Tropo code.

## 0.24.0

* Use Troposphere/CloudFormation to create API Gateway routes
  - Thanks, @mathom!
* `zappa update` now updates changes to API Gateway routes
* Redirect HTML content injection is fixed
* Redirect HTML content injection now only happens for 'text/html' content types. This is a partial solution to #303.
* Added CHANGELOG.md

## 0.0.1 - 0.23.2

* Didn't keep a changelog
* Sorry!
* Read the commit log :)
