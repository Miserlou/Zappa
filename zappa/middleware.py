from werkzeug.wsgi import ClosingIterator


def all_casings(input_string):
    """
    Permute all casings of a given string.

    A pretty algorithm, via @Amber
    http://stackoverflow.com/questions/6792803/finding-all-possible-case-permutations-in-python
    """
    if not input_string:
        yield ""
    else:
        first = input_string[:1]
        if first.lower() == first.upper():
            for sub_casing in all_casings(input_string[1:]):
                yield first + sub_casing
        else:
            for sub_casing in all_casings(input_string[1:]):
                yield first.lower() + sub_casing
                yield first.upper() + sub_casing


class ZappaWSGIMiddleware:
    """
    Middleware functions necessary for a Zappa deployment.

    Most hacks have now been remove except for Set-Cookie permutation.
    """

    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        """
        We must case-mangle the Set-Cookie header name or AWS will use only a
        single one of these headers.
        """

        def encode_response(status, headers, exc_info=None):
            """
            This makes the 'set-cookie' headers name lowercase,
            all the non-cookie headers should be sent unharmed.
            Related: https://github.com/Miserlou/Zappa/issues/1965
            """

            new_headers = [
                header
                for header in headers
                if ((type(header[0]) != str) or (header[0].lower() != "set-cookie"))
            ]
            cookie_headers = [
                (header[0].lower(), header[1])
                for header in headers
                if ((type(header[0]) == str) and (header[0].lower() == "set-cookie"))
            ]
            new_headers = new_headers + cookie_headers

            return start_response(status, new_headers, exc_info)

        # Call the application with our modifier
        response = self.application(environ, encode_response)

        # Return the response as a WSGI-safe iterator
        return ClosingIterator(response)
