import calendar
import datetime
import durationpy
import fnmatch
import json
import os
import re
import requests
import shutil
import stat
import urlparse

##
# Settings / Packaging
##

def copytree(src, dst, symlinks=False, ignore=None):
    """
    This is a contributed re-implementation of 'copytree' that
    should work with the exact same behavior on multiple platforms.

    """

    if not os.path.exists(dst):
        os.makedirs(dst)
        shutil.copystat(src, dst)
    lst = os.listdir(src)

    if ignore:
        excl = ignore(src, lst)
        lst = [x for x in lst if x not in excl]

    for item in lst:
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        if symlinks and os.path.islink(s): # pragma: no cover
            if os.path.lexists(d):
                os.remove(d)
            os.symlink(os.readlink(s), d)
            try:
                st = os.lstat(s)
                mode = stat.S_IMODE(st.st_mode)
                os.lchmod(d, mode)
            except:
                pass  # lchmod not available
        elif os.path.isdir(s):
            copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)

def parse_s3_url(url):
    """
    Parses S3 URL.

    Returns bucket (domain) and file (full path).
    """
    bucket = ''
    path = ''
    if url:
        result = urlparse.urlparse(url)
        bucket = result.netloc
        path = result.path.strip('/')
    return bucket, path

def human_size(num, suffix='B'):
    """
    Convert bytes length to a human-readable version
    """
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "{0:3.1f}{1!s}{2!s}".format(num, unit, suffix)
        num /= 1024.0
    return "{0:.1f}{1!s}{2!s}".format(num, 'Yi', suffix)

def string_to_timestamp(timestring):
    """
    Accepts a str, returns an int timestamp.
    """

    ts = None

    # Uses an extended version of Go's duration string.
    try:
        delta = durationpy.from_str(timestring);
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
        for filename in fnmatch.filter(filenames, '*settings.py'):
            full = os.path.join(root, filename)
            if 'site-packages' in full:
                continue
            full = os.path.join(root, filename)
            package_path = full.replace(os.getcwd(), '')
            package_module = package_path.replace(os.sep, '.').split('.', 1)[1].replace('.py', '')

            matches.append(package_module)
    return matches

def detect_flask_apps():
    """
    Automatically try to discover Flask apps files,
    return them as relative module paths.
    """

    matches = []
    for root, dirnames, filenames in os.walk(os.getcwd()):
        for filename in fnmatch.filter(filenames, '*.py'):
            full = os.path.join(root, filename)
            if 'site-packages' in full:
                continue

            full = os.path.join(root, filename)

            with open(full, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    app = None

                    # Kind of janky..
                    if '= Flask(' in line:
                        app = line.split('= Flask(')[0].strip()
                    if '=Flask(' in line:
                        app = line.split('=Flask(')[0].strip()

                    if not app:
                        continue

                    package_path = full.replace(os.getcwd(), '')
                    package_module = package_path.replace(os.sep, '.').split('.', 1)[1].replace('.py', '')
                    app_module = package_module + '.' + app

                    matches.append(app_module)

    return matches

##
# Async Tasks
##

def get_topic_name(lambda_name):
    """ Topic name generation """
    return '%s-zappa-async' % lambda_name

##
# Event sources / Kappa
##

def get_event_source(event_source, lambda_arn, target_function, boto_session, dry=False):
    """

    Given an event_source dictionary item, a session and a lambda_arn,
    hack into Kappa's Gibson, create out an object we can call
    to schedule this event, and return the event source.

    """
    import kappa.function
    import kappa.restapi
    import kappa.event_source.dynamodb_stream
    import kappa.event_source.kinesis
    import kappa.event_source.s3
    import kappa.event_source.sns
    import kappa.event_source.cloudwatch
    import kappa.policy
    import kappa.role
    import kappa.awsclient

    class PseudoContext(object):
        def __init__(self):
            return

    class PseudoFunction(object):
        def __init__(self):
            return

    event_source_map = {
        'dynamodb': kappa.event_source.dynamodb_stream.DynamoDBStreamEventSource,
        'kinesis': kappa.event_source.kinesis.KinesisEventSource,
        's3': kappa.event_source.s3.S3EventSource,
        'sns': kappa.event_source.sns.SNSEventSource,
        'events': kappa.event_source.cloudwatch.CloudWatchEventSource
    }

    arn = event_source['arn']
    _, _, svc, _ = arn.split(':', 3)

    event_source_func = event_source_map.get(svc, None)
    if not event_source_func:
        raise ValueError('Unknown event source: {0}'.format(arn))

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
    if svc == 's3':
        split_arn = lambda_arn.split(':')
        arn_front = ':'.join(split_arn[:-1])
        arn_back = split_arn[-1]
        ctx.environment = arn_back
        funk.arn = arn_front
        funk.name = ':'.join([arn_back, target_function])
    else:
        funk.arn = lambda_arn

    funk._context = ctx

    event_source_obj = event_source_func(ctx, event_source)

    return event_source_obj, ctx, funk

def add_event_source(event_source, lambda_arn, target_function, boto_session, dry=False):
    """
    Given an event_source dictionary, create the object and add the event source.
    """

    event_source_obj, ctx, funk = get_event_source(event_source, lambda_arn, target_function, boto_session, dry=False)
    # TODO: Detect changes in config and refine exists algorithm
    if not dry:
        if not event_source_obj.status(funk):
            event_source_obj.add(funk)
            if event_source_obj.status(funk):
                return 'successful'
            else:
                return 'failed'
        else:
            return 'exists'

    return 'dryrun'

def remove_event_source(event_source, lambda_arn, target_function, boto_session, dry=False):
    """
    Given an event_source dictionary, create the object and remove the event source.
    """

    event_source_obj, ctx, funk = get_event_source(event_source, lambda_arn, target_function, boto_session, dry=False)

    # This is slightly dirty, but necessary for using Kappa this way.
    funk.arn = lambda_arn
    if not dry:
        rule_response = event_source_obj.remove(funk)
        return rule_response
    else:
        return event_source_obj

def get_event_source_status(event_source, lambda_arn, target_function, boto_session, dry=False):
    """
    Given an event_source dictionary, create the object and get the event source status.
    """

    event_source_obj, ctx, funk = get_event_source(event_source, lambda_arn, target_function, boto_session, dry=False)
    return event_source_obj.status(funk)

##
# Analytics / Surveillance / Nagging
##

def check_new_version_available(this_version):
    """
    Checks if a newer version of Zappa is available.

    Returns True is updateable, else False.

    """

    pypi_url = 'https://pypi.python.org/pypi/Zappa/json'
    resp = requests.get(pypi_url, timeout=1.5)
    top_version = resp.json()['info']['version']

    if this_version != top_version:
        return True
    else:
        return False


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
