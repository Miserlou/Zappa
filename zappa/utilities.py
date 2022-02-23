import calendar
import datetime
import fnmatch
import io
import json
import logging
import os
import re
import shutil
import stat
import sys
from urllib.parse import urlparse

import botocore
import durationpy
from past.builtins import basestring

LOG = logging.getLogger(__name__)

##
# Settings / Packaging
##


def copytree(src, dst, metadata=True, symlinks=False, ignore=None):
    """
    This is a contributed re-implementation of 'copytree' that
    should work with the exact same behavior on multiple platforms.

    When `metadata` is False, file metadata such as permissions and modification
    times are not copied.
    """

    def copy_file(src, dst, item):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        if symlinks and os.path.islink(s):  # pragma: no cover
            if os.path.lexists(d):
                os.remove(d)
            os.symlink(os.readlink(s), d)
            if metadata:
                try:
                    st = os.lstat(s)
                    mode = stat.S_IMODE(st.st_mode)
                    os.lchmod(d, mode)
                except:
                    pass  # lchmod not available
        elif os.path.isdir(s):
            copytree(s, d, metadata, symlinks, ignore)
        else:
            shutil.copy2(s, d) if metadata else shutil.copy(s, d)

    try:
        lst = os.listdir(src)
        if not os.path.exists(dst):
            os.makedirs(dst)
            if metadata:
                shutil.copystat(src, dst)
    except NotADirectoryError:  # egg-link files
        copy_file(os.path.dirname(src), os.path.dirname(dst), os.path.basename(src))
        return

    if ignore:
        excl = ignore(src, lst)
        lst = [x for x in lst if x not in excl]

    for item in lst:
        copy_file(src, dst, item)


def parse_s3_url(url):
    """
    Parses S3 URL.

    Returns bucket (domain) and file (full path).
    """
    bucket = ""
    path = ""
    if url:
        result = urlparse(url)
        bucket = result.netloc
        path = result.path.strip("/")
    return bucket, path


def human_size(num, suffix="B"):
    """
    Convert bytes length to a human-readable version
    """
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return "{0:3.1f}{1!s}{2!s}".format(num, unit, suffix)
        num /= 1024.0
    return "{0:.1f}{1!s}{2!s}".format(num, "Yi", suffix)


def string_to_timestamp(timestring):
    """
    Accepts a str, returns an int timestamp.
    """

    ts = None

    # Uses an extended version of Go's duration string.
    try:
        delta = durationpy.from_str(timestring)
        past = datetime.datetime.utcnow() - delta
        ts = calendar.timegm(past.timetuple())
        return ts
    except Exception as e:
        pass

    if ts:
        return ts
    # else:
    #     print("Unable to parse timestring.")
    return 0


##
# `init` related
##


def detect_django_settings():
    """
    Automatically try to discover Django settings files,
    return them as relative module paths.
    """

    matches = []
    for root, dirnames, filenames in os.walk(os.getcwd()):
        for filename in fnmatch.filter(filenames, "*settings.py"):
            full = os.path.join(root, filename)
            if "site-packages" in full:
                continue
            full = os.path.join(root, filename)
            package_path = full.replace(os.getcwd(), "")
            package_module = (
                package_path.replace(os.sep, ".").split(".", 1)[1].replace(".py", "")
            )

            matches.append(package_module)
    return matches


def detect_flask_apps():
    """
    Automatically try to discover Flask apps files,
    return them as relative module paths.
    """

    matches = []
    for root, dirnames, filenames in os.walk(os.getcwd()):
        for filename in fnmatch.filter(filenames, "*.py"):
            full = os.path.join(root, filename)
            if "site-packages" in full:
                continue

            full = os.path.join(root, filename)

            with io.open(full, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines:
                    app = None

                    # Kind of janky..
                    if "= Flask(" in line:
                        app = line.split("= Flask(")[0].strip()
                    if "=Flask(" in line:
                        app = line.split("=Flask(")[0].strip()

                    if not app:
                        continue

                    package_path = full.replace(os.getcwd(), "")
                    package_module = (
                        package_path.replace(os.sep, ".")
                        .split(".", 1)[1]
                        .replace(".py", "")
                    )
                    app_module = package_module + "." + app

                    matches.append(app_module)

    return matches


def get_venv_from_python_version():
    return "python{}.{}".format(*sys.version_info)


def get_runtime_from_python_version():
    """ """
    if sys.version_info[0] < 3:
        raise ValueError("Python 2.x is no longer supported.")
    else:
        if sys.version_info[1] <= 6:
            return "python3.6"
        elif sys.version_info[1] <= 7:
            return "python3.7"
        elif sys.version_info[1] <= 8:
            return "python3.8"
        else:
            return "python3.9"


##
# Async Tasks
##


def get_topic_name(lambda_name):
    """Topic name generation"""
    return "%s-zappa-async" % lambda_name


##
# Event sources / Kappa
##


def get_event_source(
    event_source, lambda_arn, target_function, boto_session, dry=False
):
    """

    Given an event_source dictionary item, a session and a lambda_arn,
    hack into Kappa's Gibson, create out an object we can call
    to schedule this event, and return the event source.

    """
    import kappa.awsclient
    import kappa.event_source.base
    import kappa.event_source.cloudwatch
    import kappa.event_source.dynamodb_stream
    import kappa.event_source.kinesis
    import kappa.event_source.s3
    import kappa.event_source.sns
    import kappa.function
    import kappa.policy
    import kappa.restapi
    import kappa.role

    class PseudoContext:
        def __init__(self):
            return

    class PseudoFunction:
        def __init__(self):
            return

    # Mostly adapted from kappa - will probably be replaced by kappa support
    class SqsEventSource(kappa.event_source.base.EventSource):
        def __init__(self, context, config):
            super().__init__(context, config)
            self._lambda = kappa.awsclient.create_client("lambda", context.session)

        def _get_uuid(self, function):
            uuid = None
            response = self._lambda.call(
                "list_event_source_mappings",
                FunctionName=function.name,
                EventSourceArn=self.arn,
            )
            LOG.debug(response)
            if len(response["EventSourceMappings"]) > 0:
                uuid = response["EventSourceMappings"][0]["UUID"]
            return uuid

        def add(self, function):
            try:
                response = self._lambda.call(
                    "create_event_source_mapping",
                    FunctionName=function.name,
                    EventSourceArn=self.arn,
                    BatchSize=self.batch_size,
                    Enabled=self.enabled,
                )
                LOG.debug(response)
            except Exception:
                LOG.exception("Unable to add event source")

        def enable(self, function):
            self._config["enabled"] = True
            try:
                response = self._lambda.call(
                    "update_event_source_mapping",
                    UUID=self._get_uuid(function),
                    Enabled=self.enabled,
                )
                LOG.debug(response)
            except Exception:
                LOG.exception("Unable to enable event source")

        def disable(self, function):
            self._config["enabled"] = False
            try:
                response = self._lambda.call(
                    "update_event_source_mapping",
                    FunctionName=function.name,
                    Enabled=self.enabled,
                )
                LOG.debug(response)
            except Exception:
                LOG.exception("Unable to disable event source")

        def update(self, function):
            response = None
            uuid = self._get_uuid(function)
            if uuid:
                try:
                    response = self._lambda.call(
                        "update_event_source_mapping",
                        BatchSize=self.batch_size,
                        Enabled=self.enabled,
                        FunctionName=function.arn,
                    )
                    LOG.debug(response)
                except Exception:
                    LOG.exception("Unable to update event source")

        def remove(self, function):
            response = None
            uuid = self._get_uuid(function)
            if uuid:
                response = self._lambda.call("delete_event_source_mapping", UUID=uuid)
                LOG.debug(response)
            return response

        def status(self, function):
            response = None
            LOG.debug("getting status for event source %s", self.arn)
            uuid = self._get_uuid(function)
            if uuid:
                try:
                    response = self._lambda.call(
                        "get_event_source_mapping", UUID=self._get_uuid(function)
                    )
                    LOG.debug(response)
                except botocore.exceptions.ClientError:
                    LOG.debug("event source %s does not exist", self.arn)
                    response = None
            else:
                LOG.debug("No UUID for event source %s", self.arn)
            return response

    class ExtendedSnsEventSource(kappa.event_source.sns.SNSEventSource):
        @property
        def filters(self):
            return self._config.get("filters")

        def add_filters(self, function):
            try:
                subscription = self.exists(function)
                if subscription:
                    response = self._sns.call(
                        "set_subscription_attributes",
                        SubscriptionArn=subscription["SubscriptionArn"],
                        AttributeName="FilterPolicy",
                        AttributeValue=json.dumps(self.filters),
                    )
                    kappa.event_source.sns.LOG.debug(response)
            except Exception:
                kappa.event_source.sns.LOG.exception(
                    "Unable to add filters for SNS topic %s", self.arn
                )

        def add(self, function):
            super().add(function)
            if self.filters:
                self.add_filters(function)

    event_source_map = {
        "dynamodb": kappa.event_source.dynamodb_stream.DynamoDBStreamEventSource,
        "kinesis": kappa.event_source.kinesis.KinesisEventSource,
        "s3": kappa.event_source.s3.S3EventSource,
        "sns": ExtendedSnsEventSource,
        "sqs": SqsEventSource,
        "events": kappa.event_source.cloudwatch.CloudWatchEventSource,
    }

    arn = event_source["arn"]
    _, _, svc, _ = arn.split(":", 3)

    event_source_func = event_source_map.get(svc, None)
    if not event_source_func:
        raise ValueError("Unknown event source: {0}".format(arn))

    def autoreturn(self, function_name):
        return function_name

    event_source_func._make_notification_id = autoreturn

    ctx = PseudoContext()
    ctx.session = boto_session

    funk = PseudoFunction()
    funk.name = lambda_arn

    # Kappa 0.6.0 requires this nasty hacking,
    # hopefully we can remove at least some of this soon.
    # Kappa 0.7.0 introduces a whole host over other changes we don't
    # really want, so we're stuck here for a little while.

    # Related:  https://github.com/Miserlou/Zappa/issues/684
    #           https://github.com/Miserlou/Zappa/issues/688
    #           https://github.com/Miserlou/Zappa/commit/3216f7e5149e76921ecdf9451167846b95616313
    if svc == "s3":
        split_arn = lambda_arn.split(":")
        arn_front = ":".join(split_arn[:-1])
        arn_back = split_arn[-1]
        ctx.environment = arn_back
        funk.arn = arn_front
        funk.name = ":".join([arn_back, target_function])
    else:
        funk.arn = lambda_arn

    funk._context = ctx

    event_source_obj = event_source_func(ctx, event_source)

    return event_source_obj, ctx, funk


def add_event_source(
    event_source, lambda_arn, target_function, boto_session, dry=False
):
    """
    Given an event_source dictionary, create the object and add the event source.
    """

    event_source_obj, ctx, funk = get_event_source(
        event_source, lambda_arn, target_function, boto_session, dry=False
    )
    # TODO: Detect changes in config and refine exists algorithm
    if not dry:
        if not event_source_obj.status(funk):
            event_source_obj.add(funk)
            return "successful" if event_source_obj.status(funk) else "failed"
        else:
            return "exists"

    return "dryrun"


def remove_event_source(
    event_source, lambda_arn, target_function, boto_session, dry=False
):
    """
    Given an event_source dictionary, create the object and remove the event source.
    """

    event_source_obj, ctx, funk = get_event_source(
        event_source, lambda_arn, target_function, boto_session, dry=False
    )

    # This is slightly dirty, but necessary for using Kappa this way.
    funk.arn = lambda_arn
    if not dry:
        rule_response = event_source_obj.remove(funk)
        return rule_response
    else:
        return event_source_obj


def get_event_source_status(
    event_source, lambda_arn, target_function, boto_session, dry=False
):
    """
    Given an event_source dictionary, create the object and get the event source status.
    """

    event_source_obj, ctx, funk = get_event_source(
        event_source, lambda_arn, target_function, boto_session, dry=False
    )
    return event_source_obj.status(funk)


##
# Analytics / Surveillance / Nagging
##


def check_new_version_available(this_version):
    """
    Checks if a newer version of Zappa is available.

    Returns True is updateable, else False.

    """
    import requests

    pypi_url = "https://pypi.org/pypi/Zappa/json"
    resp = requests.get(pypi_url, timeout=1.5)
    top_version = resp.json()["info"]["version"]

    return this_version != top_version


class InvalidAwsLambdaName(Exception):
    """Exception: proposed AWS Lambda name is invalid"""

    pass


def validate_name(name, maxlen=80):
    """Validate name for AWS Lambda function.
    name: actual name (without `arn:aws:lambda:...:` prefix and without
        `:$LATEST`, alias or version suffix.
    maxlen: max allowed length for name without prefix and suffix.

    The value 80 was calculated from prefix with longest known region name
    and assuming that no alias or version would be longer than `$LATEST`.

    Based on AWS Lambda spec
    http://docs.aws.amazon.com/lambda/latest/dg/API_CreateFunction.html

    Return: the name
    Raise: InvalidAwsLambdaName, if the name is invalid.
    """
    if not isinstance(name, basestring):
        msg = "Name must be of type string"
        raise InvalidAwsLambdaName(msg)
    if len(name) > maxlen:
        msg = "Name is longer than {maxlen} characters."
        raise InvalidAwsLambdaName(msg.format(maxlen=maxlen))
    if len(name) == 0:
        msg = "Name must not be empty string."
        raise InvalidAwsLambdaName(msg)
    if not re.match("^[a-zA-Z0-9-_]+$", name):
        msg = "Name can only contain characters from a-z, A-Z, 0-9, _ and -"
        raise InvalidAwsLambdaName(msg)
    return name


def contains_python_files_or_subdirs(folder):
    """
    Checks (recursively) if the directory contains .py or .pyc files
    """
    for root, dirs, files in os.walk(folder):
        if [
            filename
            for filename in files
            if filename.endswith(".py") or filename.endswith(".pyc")
        ]:
            return True

        for d in dirs:
            for _, subdirs, subfiles in os.walk(d):
                if [
                    filename
                    for filename in subfiles
                    if filename.endswith(".py") or filename.endswith(".pyc")
                ]:
                    return True

    return False


def conflicts_with_a_neighbouring_module(directory_path):
    """
    Checks if a directory lies in the same directory as a .py file with the same name.
    """
    parent_dir_path, current_dir_name = os.path.split(os.path.normpath(directory_path))
    neighbours = os.listdir(parent_dir_path)
    conflicting_neighbour_filename = current_dir_name + ".py"
    return conflicting_neighbour_filename in neighbours


# https://github.com/Miserlou/Zappa/issues/1188
def titlecase_keys(d):
    """
    Takes a dict with keys of type str and returns a new dict with all keys titlecased.
    """
    return {k.title(): v for k, v in d.items()}


# https://github.com/Miserlou/Zappa/issues/1688
def is_valid_bucket_name(name):
    """
    Checks if an S3 bucket name is valid according to https://docs.aws.amazon.com/AmazonS3/latest/dev/BucketRestrictions.html#bucketnamingrules
    """
    # Bucket names must be at least 3 and no more than 63 characters long.
    if len(name) < 3 or len(name) > 63:
        return False
    # Bucket names must not contain uppercase characters or underscores.
    if any(x.isupper() for x in name):
        return False
    if "_" in name:
        return False
    # Bucket names must start with a lowercase letter or number.
    if not (name[0].islower() or name[0].isdigit()):
        return False
    # Bucket names must be a series of one or more labels. Adjacent labels are separated by a single period (.).
    for label in name.split("."):
        # Each label must start and end with a lowercase letter or a number.
        if len(label) < 1:
            return False
        if not (label[0].islower() or label[0].isdigit()):
            return False
        if not (label[-1].islower() or label[-1].isdigit()):
            return False
    # Bucket names must not be formatted as an IP address (for example, 192.168.5.4).
    looks_like_IP = True
    for label in name.split("."):
        if not label.isdigit():
            looks_like_IP = False
            break
    if looks_like_IP:
        return False

    return True


def merge_headers(event):
    """
    Merge the values of headers and multiValueHeaders into a single dict.
    Opens up support for multivalue headers via API Gateway and ALB.
    See: https://github.com/Miserlou/Zappa/pull/1756
    """
    headers = event.get("headers") or {}
    multi_headers = (event.get("multiValueHeaders") or {}).copy()
    for h in set(headers.keys()):
        if h not in multi_headers:
            multi_headers[h] = [headers[h]]
    for h in multi_headers.keys():
        multi_headers[h] = ", ".join(multi_headers[h])
    return multi_headers
