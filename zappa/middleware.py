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
        # A note about the zappa cookie: Only 1 cookie can be passed through API
        # Gateway. Hence all cookies are packed into a special cookie, the
        # zappa cookie. There are a number of problems with this:
        # * updates of single cookies, when there are multiple present results
        #   in deletion of the ones that are not being updated.
        # * expiration of cookies. The client no longer knows when cookies
        #   expires.
        # The first is solved by unpacking the zappa cookie on each request and
        # saving all incoming cookies. The response Set-Cookies are then used
        # to update the saved cookies, which are packed and set as the zappa
        # cookie.
        # The second is solved by filtering cookies on their expiration time,
        # only passing cookies that are still valid to the WSGI app.

        # Parse cookies from the WSGI environment
        encoded = parse_cookie(environ)

        # Decode the special zappa cookie if present
        if 'zappa' in encoded:
            decoded_zappa = base58.b58decode(encoded['zappa'])
            # Set the WSGI environment cookie to be the decoded value.
            # TODO: Filter cookies based on expiration
            environ[u'HTTP_COOKIE'] = decoded_zappa
            # Save the parsed cookies. We need to send them back on every update.
            request_cookies = parse_cookie(decoded_zappa)
        else:
            # No cookies were previously set
            request_cookies = dict()


        def injecting_start_response(status, headers, exc_info=None):
            # Iterate through the headers looking for Set-Cookie
            updates = False
            for idx, (header, value)  in enumerate(headers):
                if header == 'Set-Cookie':
                    # TODO: Use a different cookie parser. This one throws away
                    # stuff such as max-age, and only retains key, value.
                    cookie = parse_cookie(value)
                    # Delete the header. The cookie will be packed into the
                    # zappa cookie
                    del(headers[idx])
                    if 'zappa' in cookie:
                        # TODO: Figure out why this would ever happen. Observed
                        # by Doerge during dev.
                        # We found a header in the response object that sets
                        # zappa as a cookie. This shouldn't happen. Delete it.
                        del(cookie['zappa'])
                    if cookie:
                        # Mark that we have an update to send
                        updates = True
                        # Update the request_cookies with the cookie
                        request_cookies.update(cookie)

            # Encode cookies into Zappa cookie, if there were any changes
            if updates and request_cookies:
                # Create a list of "name=value" of all request_cookies
                final_cookies = ["{cookie}={value}".format(cookie=k, value=v) for k, v in request_cookies.items()]
                # Join them into one big cookie, and encode them
                encoded = base58.b58encode(';'.join(final_cookies))
                # Set the result as the zappa cookie
                headers.append(('Set-Cookie', dump_cookie('zappa', value=encoded)))

            return start_response(status, headers, exc_info)

        # Call the wrapped WSGI-application with the modified WSGI environment
        # and propagate the response to caller
        return ClosingIterator(self.application(environ, injecting_start_response))
