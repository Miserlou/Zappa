# Zappa Example

This will deploy a simple Flask app

## Setup
    # configure your AWS keys
    $ aws configure

## Deploy WSGI App
    # deploy API to dev environment
    $ zappa deploy dev_api

    # Zappa will creates the API Gateway url for you similar to this
    $ curl https://zzz.execute-api.us-west-2.amazonaws.com/dev_api

## Schedule

You can deploy just a function with a schedule:

    # deploy API to dev environment (doesn't create APIGateway resource)
    $ zappa deploy dev_event

    # schedule CloudWatch to run this Lambda function every minute
    $ zappa schedule dev_event

    # watch log
    $ zappa log dev_event

You can also call a scheduled function packaged along with your normal WSGI app:

    # deploy API to prod environment
    $ zappa deploy prod

    # schedule CloudWatch to run mymodule.myfunc every 5 minutes
    $ zappa schedule prod

This function can optionally take the usual `event` and `context` lambda arguments.

## Local Testing

To test locally you can execute the WSGI app like you would normally.

    $ python app.py

You can also call your scheduled function locally. When deployed, the handler will import and run this function.
For example, in "prod" it is defined as "mymodule.myfunc", so it can be called as such:

    $ python -c "import mymodule; mymodule.myfunc()"

