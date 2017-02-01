from werkzeug.wsgi import ClosingIterator


def all_casings(input_string):
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
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        """
        We must case-mangle the Set-Cookie header name or AWS will use only a
        single one of these headers.
        """

        def encode_response(status, headers, exc_info=None):
            # All the non-cookie headers should be sent unharmed.
            new_headers = [(header[0], header[1]) for header in headers if
                           header[0] != 'Set-Cookie']
            cookie_headers = [x for x in headers if x[0] == "Set-Cookie"]
            for header, new_name in zip(cookie_headers,
                                        all_casings("Set-Cookie")):
                new_headers.append((new_name, header[1]))
            return start_response(status, new_headers, exc_info)

        # Call the application with our modifier
        response = self.application(environ, encode_response)

        # Return the response as a WSGI-safe iterator
        return ClosingIterator(response)
