![Logo placeholder](http://i.imgur.com/vLflpND.gif)
# Zappa [![Build Status](https://travis-ci.org/Miserlou/Zappa.svg)](https://travis-ci.org/Miserlou/Zappa)
#### Serverless WSGI with AWS Lambda + API Gateway

Zappa makes it super easy to deploy all Python WSGI applications on AWS Lambda + API Gateway. Think of it as "serverless" web hosting for your Python web apps.

That means:

* **No more** tedious web server configuration!
* **No more** paying for 24/7 server uptime!
* **No more** worrying about load balancing / scalability!
* **No more** worrying about keeping servers online!

__Awesome!__

This project is for the Zappa core library, which can be used by any WSGI-compatible web framework (which is pretty much all of them.) This library also handles:

* Packaging projects into Lambda-ready zip files and uploading them to S3
* Correctly setting up IAM roles and permissions
* Automatically configuring API Gateway routes, methods and integration responses
* Deploying the API to various stages of readiness

If you are looking for the version for your favorite web frameworks, you should probably try here:

* **[django-zappa](https://github.com/Miserlou/django-zappa)**
* **[flask-zappa](https://github.com/Miserlou/flask-zappa)**
* **pyramid-zappa** (Coming.. maybe?)

## Usage

If you just want to use Zappa to deploy your web application, you'll probably want to use a client library like [django-zappa](https://github.com/Miserlou/django-zappa) instead. But, if you want to create a new client library or use Zappa directly, you can follow the steps below.

You can install Zappa through pip:

    $ pip install zappa

Then, you'll want to call its main capabilities in order:

```python

# Set your configuration
project_name = "MyProject"
api_stage = "Production"
s3_bucket_name = 'MyLambdaBucket'

# Make your Zappa object
zappa = Zappa()

# Load your AWS credentials from ~/.aws/credentials
zappa.load_credentials()

# Make sure the necessary IAM execution roles are available
zappa.create_iam_roles()

# Create the Lambda zip package (includes project and virtualenvironment)
zip_path = zappa.create_lambda_zip(project_name)

# Upload it to S3
zip_arn = zappa.upload_to_s3(zip_path, s3_bucket_name)

# Register the Lambda function with that zip as the source
# You'll also need to define the path to your lambda_handler code.
lambda_arn = zappa.create_lambda_function(s3_bucket_name, zip_path, project_name, 'runme.lambda_handler')

# Create and configure the API Gateway
api_id = zappa.create_api_gateway_routes(lambda_arn)

# Deploy the API!
endpoint_url = zappa.deploy_api_gateway(api_id, api_stage)

print("Your Zappa deployment is live!: " + endpoint_url)
```

And your application is [live](https://7k6anj0k99.execute-api.us-east-1.amazonaws.com/prod)!

## Hacks

Zappa goes quite far beyond what Lambda and API Gateway were ever intended to handle. As a result, there are quite a few hacks in here that allow it to work. Some of those include, but aren't limited to..

* Using VTL to map body, headers, method, params and query strings into JSON, and then turning that into valid WSGI.
* Attaching response codes to response bodies, Base64 encoding the whole thing, using that as a regex to route the response code, decoding the body in VTL, and mapping the response body to that.
* Packing and _Base58_ encoding multiple cookies into a single cookie because we can only map one kind.
* Turning cookie-setting 301/302 responses into 200 responses with HTML redirects, because we have no way to set headers on redirects.

## Sites Using Zappa

* [zappa.gun.io](https://zappa.gun.io) - A Zappa "Hello, World" (real homepage coming.. soon..)
* [spheres.gun.io](https://spheres.gun.io)  - Spheres, a photosphere host and viewer
* Your site here? 

## TODO

This project is very young, so there is still plenty to be done. Contributions are more than welcome! Please file tickets before submitting patches, and submit your patches to the 'dev' branch.

Things that need work right now:

* Testing
* Clients for frameworks besides Django
* Feedback
* Real documentation / website!
