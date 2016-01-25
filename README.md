# Zappa
#### Easily WSGI Web Applications on AWS Lambda + API Gateway

Zappa makes it super easy to deploy Python WSGI applications on on AWS Lambda + API Gateway. Think of it as "serverless" web hosting for your Python web apps.

That means:

    * No more having to fiddle with web servers to deploy your applications!
    * No more worrying about **keeping servers online**!
    * No more paying for 24/7 server uptime!
    * No more worrying about load balancing / scalability!

Awesome!

This project is for the Zappa core library, which can be used by an WSGI-compatible web framework (which is pretty much all of them.) This library also handles:

    * Packaging projects into Lambda-ready zip files and uploading them to S3
    * Correctly setting up IAM roles and permissions
    * Automatically configuring API Gateway routes, methods and integration responses
    * Deploying the API to various stages of readiness

If you are looking for the version for your favorite web frameworks, you should probably try here:

    * [django-zappa](https://github.com/Miserlou/django-zappa)
    * flask-zappa (Coming soon!)
    * pyramid-zappa (Coming.. maybe?)

## Usage

If you just want to use Zappa to deploy your web application, you'll probably want to use a client library like [django-zappa](https://github.com/Miserlou/django-zappa) instead. But, if you want to create a new client library or use Zappa directly, you can follow the steps below.

You can install Zappa through pip:

    $ pip install zappa

Then, you'll want to call its main capabilities in order:

    ```python
    zappa = Zappa()
    zappa.load_credentials()
    zappa.create_iam_roles()

    project_name = "MyProject"
    api_stage = "Production"
    s3_bucket_name = 'MyLambdaBucket'

    zip_path = zappa.create_lambda_zip(project_name)
    zip_arn = zappa.upload_to_s3(zip_path, s3_bucket_name)
    lambda_arn = zappa.create_lambda_function(s3_bucket_name, zip_path, project_name, 'runme.lambda_handler')

    api_id = zappa.create_api_gateway_routes(lambda_arn)
    endpoint_url = zappa.deploy_api_gateway(api_id, api_stage)

    print("Your Zappa deployment is live!: " + endpoint_url)
    ```

And your application is [live](https://7k6anj0k99.execute-api.us-east-1.amazonaws.com/prod)!

## TODO

This project is very young, so there is still plenty to be done. Contributions are more than welcome! Please file tickets before submitting patches, and submit your patches to the 'dev' branch.

Things that need work right now:

    * Testing
    * Route53 Integration
    * SSL Integration
    * Clients for frameworks besides Django
    * Package size/speed optimization
    * Feedback
    * A nifty logo
