import placebo
import boto3
import os
import functools
from contextlib import contextmanager
from mock import patch, MagicMock

try:
    file
except NameError:  # builtin 'file' was removed in Python 3
    from io import IOBase as file

PLACEBO_DIR = os.path.join(os.path.dirname(__file__), "placebo")


def placebo_session(function):
    """
    Decorator to help do testing with placebo.

    Simply wrap the function you want to test and make sure to add
    a "session" argument so the decorator can pass the placebo session.

    Accepts the following environment variables to configure placebo:

    PLACEBO_MODE: set to "record" to record AWS calls and save them
    PLACEBO_PROFILE: optionally set an AWS credential profile to record with
    """

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        session_kwargs = {
            "region_name": os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        }
        profile_name = os.environ.get("PLACEBO_PROFILE", None)
        if profile_name:
            session_kwargs["profile_name"] = profile_name

        session = boto3.Session(**session_kwargs)

        self = args[0]
        prefix = self.__class__.__name__ + "." + function.__name__
        record_dir = os.path.join(PLACEBO_DIR, prefix)

        if not os.path.exists(record_dir):
            os.makedirs(record_dir)

        pill = placebo.attach(session, data_path=record_dir)

        if os.environ.get("PLACEBO_MODE") == "record":
            pill.record()
        else:
            pill.playback()

        kwargs["session"] = session

        return function(*args, **kwargs)

    return wrapper


@contextmanager
def patch_open():
    """Patch open() to allow mocking both open() itself and the file that is
    yielded.
    Yields the mock for "open" and "file", respectively."""
    mock_open = MagicMock(spec=open)
    mock_file = MagicMock(spec=file)

    @contextmanager
    def stub_open(*args, **kwargs):
        mock_open(*args, **kwargs)
        yield mock_file

    with patch("__builtin__.open", stub_open):
        yield mock_open, mock_file
