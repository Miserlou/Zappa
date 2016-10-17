# Zappa Changelog

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
