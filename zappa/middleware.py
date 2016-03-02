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


def decode_zappa_cookie(encoded_zappa):
    decoded_zappa = base58.b58decode(encoded_zappa)
    # Set the WSGI environment cookie to be the decoded value.
    # TODO: Filter cookies based on expiration
    # Save the parsed cookies. We need to send them back on every update.
    request_cookies = parse_cookie(decoded_zappa)
    return decoded_zappa, request_cookies


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

        # Decode the special zappa cookie if present in the request
        if 'zappa' in encoded:
            # Save the parsed cookies. We need to send them back on every update.
            decoded_zappa, request_cookies = decode_zappa_cookie(encoded['zappa'])
            # Set the WSGI environment cookie to be the decoded value.
            environ[u'HTTP_COOKIE'] = decoded_zappa
        else:
            # No cookies were previously set
            request_cookies = dict()

        def injecting_start_response(status, headers, exc_info=None):
            # All the non-cookie headers should be sent
            new_headers = [(x[0], x[1]) for x in headers if x[0] != 'Set-Cookie']

            updates = False
            # Filter the headers for Set-Cookie header
            # cookie_dicts is a list of dicts
            cookie_dicts = [parse_cookie(x[1]) for x in headers if x[0] == 'Set-Cookie']
            # is a list of dicts that contain 'zappa'
            zappa_cookies = [d for d in cookie_dicts if 'zappa' in d]
            try:
                # If we receive a zappa cookie here, decode it and append the
                # cookies inside it to the cookie list
                _, zappa_content = decode_zappa_cookie(zappa_cookies[0]['zappa'])
                cookie_dicts.append(zappa_content)
            except (IndexError, KeyError):
                # There were no zappa cookies present.
                # Ignore.
                pass

            # Flatten cookies_dicts to one dict. If there are multiple occuring
            # cookies, the last one present in the headers wins.
            cookies = dict()
            map(cookies.update, cookie_dicts)

            # Update request_cookies with cookies from the response
            for name, value in cookies.items():
                if name == 'zappa':
                    continue
                try:
                    value_old = request_cookies[name]
                except KeyError:
                    # The cookie was not previously set
                    request_cookies[name] = value
                    updates = True
                else:
                    if value != value_old:
                        # Update the request_cookies with the cookie
                        request_cookies[name] = value
                        updates = True

            # Pack the cookies
            # Encode cookies into Zappa cookie, if there were any changes
            if updates and request_cookies:
                # Create a list of "name=value" of all request_cookies
                final_cookies = ["{cookie}={value}".format(cookie=k, value=v) for k, v in request_cookies.items()]
                # Join them into one big cookie, and encode them
                encoded = base58.b58encode(';'.join(final_cookies))
                # Set the result as the zappa cookie

                new_headers.append(
                    ('Set-Cookie', dump_cookie('zappa', value=encoded))
                )

            return start_response(status, new_headers, exc_info)

        # Call the wrapped WSGI-application with the modified WSGI environment
        # and propagate the response to caller
        return ClosingIterator(
            self.application(environ, injecting_start_response)
        )
