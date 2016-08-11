=====
Hacks
=====

Zappa goes quite far beyond what Lambda and API Gateway were ever intended to handle. As a result, there are quite a few hacks in here that allow it to work. Some of those include, but aren't limited to..

* Using VTL to map body, headers, method, params and query strings into JSON, and then turning that into valid WSGI.
* Attaching response codes to response bodies, Base64 encoding the whole thing, using that as a regex to route the response code, decoding the body in VTL, and mapping the response body to that.
* Packing and _Base58_ encoding multiple cookies into a single cookie because we can only map one kind.
* Turning cookie-setting 301/302 responses into 200 responses with HTML redirects, because we have no way to set headers on redirects.