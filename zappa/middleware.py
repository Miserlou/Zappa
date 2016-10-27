import base58
import json
import time

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

    # Unpacked / Before Packed Cookies
    decoded_zappa = None
    request_cookies = {}

    start_response = None
    redirect_content = None

    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        """
        A note about the zappa cookie: Only 1 cookie can be passed through API
        Gateway. Hence all cookies are packed into a special cookie, the
        zappa cookie. There are a number of problems with this:

            * updates of single cookies, when there are multiple present results
              in deletion of the ones that are not being updated.
            * expiration of cookies. The client no longer knows when cookies
              expires.

        The first is solved by unpacking the zappa cookie on each request and
        saving all incoming cookies. The response Set-Cookies are then used
        to update the saved cookies, which are packed and set as the zappa
        cookie.

        The second is solved by filtering cookies on their expiration time,
        only passing cookies that are still valid to the WSGI app.
        """
        self.start_response = start_response

        # Parse cookies from the WSGI environment
        parsed = parse_cookie(environ)

        # Decode the special zappa cookie if present in the request
        if 'zappa' in parsed:

            # Save the parsed cookies. We need to send them back on every update.
            self.decode_zappa_cookie(parsed['zappa'])

            # Since the client doesn't know it has old cookies,
            # manual expire them.
            self.filter_expired_cookies()

            # Set the WSGI environment cookie to be the decoded value.
            environ[u'HTTP_COOKIE'] = self.cookie_environ_string()
        else:
            # No cookies were previously set
            self.request_cookies = dict()

        # Call the application with our modifier
        response = self.application(environ, self.encode_response)

        # If we have a redirect, smash in our response content.
        if self.redirect_content:
            response = [self.redirect_content for item in response]

        self.redirect_content = None # Make sure that nothing is cached from a previous request

        # Return the response as a WSGI-safe iterator
        return ClosingIterator(
            response
        )

    def encode_response(self, status, headers, exc_info=None):
        """
        Zappa-ify our application response!

        This means:
            - Updating any existing cookies.
            - Packing all our cookies into a single ZappaCookie.
            - Injecting redirect HTML if setting a Cookie on a redirect.

        """
        # All the non-cookie headers should be sent unharmed.
        new_headers = [(header[0], header[1]) for header in headers if header[0] != 'Set-Cookie']

        # Filter the headers for Set-Cookie header
        cookie_dicts = [
            {header[1].split('=', 1)[0].strip():header[1].split('=', 1)[1]}
            for header
            in headers
            if header[0] == 'Set-Cookie'
        ]

        # Update request_cookies with cookies from the response. If there are
        # multiple occuring cookies, the last one present in the headers wins.
        map(self.request_cookies.update, cookie_dicts)

        # Get the oldest expire time, and set the Zappa cookie age to that.
        # Else, let this be a session cookie.
        expires = None
        for _, exp in self.iter_cookies_expires():
            if exp > expires:
                expires = exp

        # JSON-ify the cookie and encode it.
        pack_s = json.dumps(self.request_cookies)
        encoded = base58.b58encode(pack_s)

        # Set the result as the zappa cookie
        new_headers.append(
            (
                'Set-Cookie',
                dump_cookie('zappa', value=encoded, expires=expires)
            )
        )

        # If setting cookie on a 301/2,
        # return 200 and replace the content with a javascript redirector
        # content_type_header_key = [k for k, v in enumerate(new_headers) if v[0] == 'Content-Type']
        # if len(content_type_header_key) > 0:
        #     if "text/html" in new_headers[content_type_header_key[0]][1]:
        #         if status != '200 OK':
        #             for key, value in new_headers:
        #                 if key != 'Location':
        #                     continue
        #                 self.redirect_content = REDIRECT_HTML.replace('REDIRECT_ME', value)
        #                 status = '200 OK'
        #                 break

        return self.start_response(status, new_headers, exc_info)

    def decode_zappa_cookie(self, encoded_zappa):
        """
        Eat our Zappa cookie.
        Save the parsed cookies, as we need to send them back on every update.
        """
        self.decoded_zappa = base58.b58decode(encoded_zappa)
        self.request_cookies = json.loads(self.decoded_zappa)

    def filter_expired_cookies(self):
        """
        Remove any expired cookies from our internal state.

        The browser may send expired cookies, because it does not parse the
        the ZappaCookie into its constituent parts.
        """
        now = time.gmtime()  # GMT as struct_time
        for name, exp in self.iter_cookies_expires():
            if exp < now:
                del(self.request_cookies[name])

    def iter_cookies_expires(self):
        """
            Interator over request_cookies.
            Yield name and expires of cookies.
        """
        for name, value in self.request_cookies.items():
            cookie = (name + '=' + value).encode('utf-8')
            if cookie.count('=') is 1:
                continue

            kvps = cookie.split(';')
            for kvp in kvps:
                kvp = kvp.strip()
                if 'expires' in kvp.lower():
                    try:
                        exp = time.strptime(kvp.split('=')[1], "%a, %d-%b-%Y %H:%M:%S GMT")
                    except ValueError:  # https://tools.ietf.org/html/rfc6265#section-5.1.1
                        exp = time.strptime(kvp.split('=')[1], "%a, %d-%b-%y %H:%M:%S GMT")
                    yield name, exp
                    break

    def cookie_environ_string(self):
        """
        Return the current set of cookies as a string for the HTTP_COOKIE environ.
        """
        return ';'.join([key + '=' + value for key, value in self.request_cookies.items()])
