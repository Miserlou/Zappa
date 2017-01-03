from cgi import parse_qs, escape

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

def callback(self):
    print("this is a callback")

def prebuild_me():
    print("this is a prebuild script")

