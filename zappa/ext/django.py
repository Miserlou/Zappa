import sys

# add the Lambda root path into the sys.path
sys.path.append('/var/task')

from django.core.handlers.wsgi import WSGIHandler
from django.core.wsgi import get_wsgi_application
import os

def get_django_wsgi(settings_module):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

    import django
    django.setup()

    return get_wsgi_application()