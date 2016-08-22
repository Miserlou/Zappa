import sys
import os

# add the Lambda root path into the sys.path
sys.path.append('/var/task')

# We're not going to require importing all of Django just to test.
try: # pragma: no cover
    from django.core.handlers.wsgi import WSGIHandler
    from django.core.wsgi import get_wsgi_application
except ImportError as e:
    pass

def get_django_wsgi(settings_module): # pragma: no cover
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

    import django
    django.setup()

    return get_wsgi_application()