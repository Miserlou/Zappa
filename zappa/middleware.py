import base58
import json
from werkzeug.wrappers import Request, Response
from werkzeug.http import parse_cookie, dump_cookie

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
        # print "ZappaWSGIMiddleware environ = ", environ

        # print 'unparsed environ', environ
        
        # Parse cookies from WSGI environment
        encoded = parse_cookie(environ)
        # Decode Zappa cookie if present
        if 'zappa' in encoded:
            decoded = base58.b58decode(encoded['zappa'])
            # Set the WSGI environments cookie to be the decoded value.
            environ[u'HTTP_COOKIE'] = decoded
        print 'parsed environ', environ

        # Call the wrapped WSGI-application with the modified WSGI environment
        response = Response.from_app(self.application, environ)
        print "got response", response.headers
        # Encode cookies into Zappa cookie
        try:
            cookies = []
            for (header, value)  in response.headers:
                if header == 'Set-Cookie':
                    cookie = parse_cookie(value)
                    cookie_vals = [dump_cookie(c[0], c[1]) for c in cookie.items() if c[0] != 'zappa']
                    cookies.extend(cookie_vals)
                    # print 'cookies', cookies
                    # zappa_cookie = json.dumps(cookies)
                    # print 'zappa_cookie', zappa_cookie
                    # zappa_cookies.append(value)
            print 'cookies', cookies
            if cookies:
                encoded = base58.b58encode(';'.join(cookies))
                # print 'encoded', encoded
                response.headers['Set-Cookie'] = dump_cookie('zappa', value=encoded)
        except KeyError as e:
            pass
        except Exception as e:
            print "Error occured", e
            raise e

        # print "encoded headers =", response.headers

        # Propagate the response to caller
        return response(environ, start_response)
