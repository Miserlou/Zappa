import sys

# add the hellodjango project path into the sys.path
sys.path.append('/var/task')

# # add the virtualenv site-packages path to the sys.path
# sys.path.append('<PATH_TO_VIRTUALENV>/Lib/site-packages')

from django.core.handlers.wsgi import WSGIHandler
from django.core.wsgi import get_wsgi_application
import os

def get_django_wsgi(settings_module):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

    import django
    django.setup()

    return get_wsgi_application()