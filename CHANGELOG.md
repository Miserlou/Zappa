# Zappa Changelog

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
* Small refactors and dependancy upgrades.

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
* Bump dependancies - make sure you reinstall your requirements!
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
