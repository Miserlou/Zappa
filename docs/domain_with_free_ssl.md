# Using Let's Encrypt with Zappa (HTTP Validation)

## IMPORTANT!: Zappa now supports DNS-based validation out of the box, so you should probably use that if possible!

This guide will show you the slightly convoluted way of running a Zappa website on an API Gateway Custom Domain Name with a free valid SSL certificate via Let's Encrypt with HTTP validation.

## Tool Installation

First, you should have a valid Zappa website deployed to API Gateway without a domain.

You'll also need to install Let's Encrypt via git:

```
$ git clone https://github.com/letsencrypt/letsencrypt
$ cd letsencrypt
```

and localtunnel via npm:

```
$ npm install -g localtunnel
```

## Generating the Certificate

In one terminal, run:

```
./letsencrypt-auto certonly -d yoursub.example.com --manual
```

Hit 'Yes' until you get to a message like this:

```
Make sure your web server displays the following content at
http://yoursub.example.com/.well-known/acme-challenge/OJkbegasdfnowA_xql_kqpl8hBImj9WbM88fDF35wBE before continuing:

OJkbegIsNpnowA_xql_kqpl8hBImj9WbM88fDF35wBE.Dowxk8snntasdfS433FYr2xtYZ0RaBcpaEXqmdc

If you don't have HTTP server configured, you can run the following
command on the target server (as root):

mkdir -p /tmp/letsencrypt/public_html/.well-known/acme-challenge
cd /tmp/letsencrypt/public_html
printf "%s" OJkbegIsNpnowA_xql_kqpl8hBImj9WbM88fDF35wBE.Dowxk8snnt2LxVZS3XS433FYr2xtYZ0RaBcpaEXqmdc > .well-known/acme-challenge/OJkbegIsNpnowA_xql_kqpl8hBImj9WbM88fDF35wBE
# run only once per server:
$(command -v python2 || command -v python2.7 || command -v python2.6) -c \
"import BaseHTTPServer, SimpleHTTPServer; \
s = BaseHTTPServer.HTTPServer(('', 80), SimpleHTTPServer.SimpleHTTPRequestHandler); \
s.serve_forever()"
Press ENTER to continue
```

Next, in another terminal, run the command it gave you as root.
```
sudo $(command -v python2 || command -v python2.7 || command -v python2.6) -c \
"import BaseHTTPServer, SimpleHTTPServer; \
s = BaseHTTPServer.HTTPServer(('', 80), SimpleHTTPServer.SimpleHTTPRequestHandler); \
s.serve_forever()"
```

In a third terminal, run the following command (make sure firewall is off or allow port 80 through):

```
lt --port 80 --subdomain yoursub
```

Then, in a browser, visit http://yoursub.localtunnel.me/.well-known/acme-challenge/ and make sure that your challenge value is there.

Next, point your DNS server's CNAME value to be "yoursub.localtunnel.me". Wait five minutes for this to propate, then visit http://yoursub.example.com/.well-known/acme-challenge/ and confirm that this is working.

Then, in the first terminal, press ENTER and your certificate will be generated. You can find all of the keys and certificates in /etc/letsencrypt/live/yoursub.example.com/

## Installing the Certificate

In the AWS API Gateway console, visit the [custom domains](https://console.aws.amazon.com/apigateway/home?region=us-east-1#/custom-domain-names) page. Press 'create' and fill in your values from your /etc/letsencrypt/live/yoursub.example.com/ directory.


| value | AWS API Gateway Custom Domain Name Setting field |
| --- | --- | --- |
| `yoursub.example.com` | Domain name |
| `yoursub.example.com` | Certificate name |
| `privkey.pem` | Certificate private key |
| `cert.pem` | Certificate body |
| `fullchain.pem` | Certificate chain. **Note**: only copy the 2nd part of the chain because the 1st part is the Certificate body, already provided.

Finally, press 'Save' and your domain with a free valid SSL certificate will be live! Update your domain DNS CNAME to point to API Gateway domain. Also, this certificate will expire after 90 days, remember to re-generate it!
