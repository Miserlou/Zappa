import base58
from werkzeug.http import parse_cookie, dump_cookie
from werkzeug.wsgi import ClosingIterator

REDIRECT_HTML = """<!DOCTYPE HTML>
<html lang="en-US">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="1;url=REDIRECT_ME">
        <script type="text/javascript">
            window.location.href = "REDIRECT_ME"
        </script>
        <title>Page Redirection</title>
    </head>
    <body>
        <!-- Note: don't tell people to `click` the link, just tell them that it is a link. -->
        If you are not redirected automatically, follow the <a href='REDIRECT_ME'>link to example</a>
    </body>
</html>"""

class ZappaWSGIMiddleware(object):
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        # Parse cookies from the WSGI environment
        encoded = parse_cookie(environ)

        # Decode the special zappa cookie if present
        if 'zappa' in encoded:
            decoded_zappa = base58.b58decode(encoded['zappa'])
            # Set the WSGI environment cookie to be the decoded value.
            environ[u'HTTP_COOKIE'] = decoded_zappa
            # Save the parsed cookies. We need to send them back on every update.
            request_cookies = parse_cookie(decoded_zappa)
        else:
            request_cookies = dict()


        def injecting_start_response(status, headers, exc_info=None):
            # Iterate through the headers looking for Set-Cookie
            updates = False
            for idx, (header, value)  in enumerate(headers):
                if header == 'Set-Cookie':
                    cookie = parse_cookie(value)
                    if 'zappa' in cookie:
                        # We found a header in the response object that sets
                        # zappa as a cookie. Delete it.
                        del(headers[idx])
                        del(cookie['zappa'])
                        print 'deleted zappa set-cooke header'
                        print 'remaining cookie', cookie
                    if cookie:
                        updates = True
                        request_cookies.update(cookie)
                        print 'setting cookie', cookie

            # Encode cookies into Zappa cookie
            if updates and request_cookies:
                final_cookies = ["{cookie}={value}".format(cookie=k, value=v) for k, v in request_cookies.items()]
                encoded = base58.b58encode(';'.join(final_cookies))
                headers.append(('Set-Cookie', dump_cookie('zappa', value=encoded)))

            return start_response(status, headers, exc_info)

        # Call the wrapped WSGI-application with the modified WSGI environment
        # and propagate the response to caller
        return ClosingIterator(self.application(environ, injecting_start_response))
