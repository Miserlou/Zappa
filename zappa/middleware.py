import base58
import json
from werkzeug.wrappers import Request, Response
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
        # print "ZappaWSGIMiddleware environ = ", environ

        # print 'unparsed environ', environ
        
        # Parse cookies from WSGI environment
        encoded = parse_cookie(environ)
        print 'encoded', encoded
        # Decode Zappa cookie if present
        if 'zappa' in encoded:
            decoded_zappa = base58.b58decode(encoded['zappa'])
            # Set the WSGI environments cookie to be the decoded value.
            environ[u'HTTP_COOKIE'] = decoded_zappa
            request_cookies = parse_cookie(decoded_zappa)
        else:
            request_cookies = dict()
        print 'request_cookies start', request_cookies
        print 'parsed environ', environ

        def injecting_start_response(status, headers, exc_info=None):

        # Call the wrapped WSGI-application with the modified WSGI environment
        # response = Response.from_app(self.application, environ)
        # print "got response", response.headers

            # Encode cookies into Zappa cookie
            cookies = []
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
                    # cookies = {k: v for k,v in cookie.items()}
                    if cookie:
                        request_cookies.update(cookie)
                        updates = True
                        # cookies.extend(cookie_vals)
                        # print 'cookies', cookies
                        # zappa_cookie = json.dumps(cookies)
                        # print 'zappa_cookie', zappa_cookie
                        # zappa_cookies.append(value)
                        print 'setting cookie', cookie
            # print 'cookies', cookies

            print 'request_cookies', json.dumps(request_cookies, indent=4)
            if updates and request_cookies:
                final_cookies = ["{cookie}={value}".format(cookie=k, value=v) for k, v in request_cookies.items()]
                encoded = base58.b58encode(';'.join(final_cookies))
                # print 'encoded', encoded
                headers.append(('Set-Cookie', dump_cookie('zappa', value=encoded)))
            return start_response(status, headers, exc_info)

        return ClosingIterator(self.application(environ, injecting_start_response))

        # print "final headers =", headers

        # Propagate the response to caller
        # return response(environ, start_response)
