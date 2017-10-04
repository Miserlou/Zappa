from werkzeug.wsgi import ClosingIterator


def all_casings(input_string):
    """
    Permute all casings of a given string.

    A pretty algoritm, via @Amber
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


class ZappaWSGIMiddleware(object):
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
            Create an APIGW-acceptable version of our cookies.

            We have to use a bizarre hack that turns multiple Set-Cookie headers into
            their case-permutated format, ex:

            Set-cookie:
            sEt-cookie:
            seT-cookie:

            To get around an API Gateway limitation.

            This is weird, but better than our previous hack of creating a Base58-encoded
            supercookie.
            """

            # All the non-cookie headers should be sent unharmed.
            
            # The main app can send 'set-cookie' headers in any casing
            # Related: https://github.com/Miserlou/Zappa/issues/990
            new_headers = [header for header in headers
                           if ((type(header[0]) != str) or (header[0].lower() != 'set-cookie'))]
            cookie_headers = [header for header in headers 
                              if ((type(header[0]) == str) and (header[0].lower() == "set-cookie"))]
            for header, new_name in zip(cookie_headers,
                                        all_casings("Set-Cookie")):
                new_headers.append((new_name, header[1]))
            return start_response(status, new_headers, exc_info)

        # Call the application with our modifier
        response = self.application(environ, encode_response)

        # Return the response as a WSGI-safe iterator
        return ClosingIterator(response)
