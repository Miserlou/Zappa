from urlparse import parse_qs

from werkzeug.utils import escape


def hello_world(environ, start_response):
    parameters = parse_qs(environ.get('QUERY_STRING', ''))
    if 'subject' in parameters:
        subject = escape(parameters['subject'][0])
    else:
        subject = 'World'
    start_response('200 OK', [('Content-Type', 'text/html')])
    return ['''Hello {subject!s}
    Hello {subject!s}!

'''.format(**{'subject': subject})]


def schedule_me():
    return "Hello!"
