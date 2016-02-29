import placebo
import boto3
import os
import functools

PLACEBO_DIR = os.path.join(os.path.dirname(__file__), 'placebo')


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
            'region_name': os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
        }
        profile_name = os.environ.get('PLACEBO_PROFILE', None)
        if profile_name:
            session_kwargs['profile_name'] = profile_name

        session = boto3.Session(**session_kwargs)

        self = args[0]
        prefix = self.__class__.__name__ + '.' + function.__name__
        record_dir = os.path.join(PLACEBO_DIR, prefix)

        if not os.path.exists(record_dir):
            os.makedirs(record_dir)

        pill = placebo.attach(session, data_path=record_dir)

        if os.environ.get('PLACEBO_MODE') == 'record':
            pill.record()
        else:
            pill.playback()

        kwargs['session'] = session

        return function(*args, **kwargs)

    return wrapper
