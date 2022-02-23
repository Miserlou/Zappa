from zappa.asynchronous import task

try:
    from urllib.parse import parse_qs
except ImportError:
    from cgi import parse_qs

try:
    from html import escape
except ImportError:
    from cgi import escape


def hello_world(environ, start_response):
    parameters = parse_qs(environ.get("QUERY_STRING", ""))
    if "subject" in parameters:
        subject = escape(parameters["subject"][0])
    else:
        subject = "World"
    start_response("200 OK", [("Content-Type", "text/html")])
    return [
        """Hello {subject!s}
    Hello {subject!s}!

""".format(
            **{"subject": subject}
        )
    ]


def schedule_me():
    return "Hello!"


@task
def async_me(arg1, **kwargs):
    return "run async when on lambda %s%s" % (arg1, kwargs.get("foo", ""))


@task(remote_aws_lambda_function_name="test-app-dev", remote_aws_region="us-east-1")
def remote_async_me(arg1, **kwargs):
    return "run async always on lambda %s%s" % (arg1, kwargs.get("foo", ""))


def callback(self):
    print("this is a callback")


def prebuild_me():
    print("this is a prebuild script")
