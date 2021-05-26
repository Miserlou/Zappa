import os
import sys

# add the Lambda root path into the sys.path
sys.path.append("/var/task")


def get_django_wsgi(settings_module):
    from django.core.wsgi import get_wsgi_application

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

    import django

    if django.VERSION[0] <= 1 and django.VERSION[1] < 7:
        # call django.setup only for django <1.7.0
        # (because setup already in get_wsgi_application since that)
        # https://github.com/django/django/commit/80d74097b4bd7186ad99b6d41d0ed90347a39b21
        django.setup()

    return get_wsgi_application()
