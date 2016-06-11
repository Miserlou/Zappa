# Zappa Example

This will deploy a simple Flask app

## Setup
    # configure your AWS keys
    $ aws configure

## Deploy
    # deploy API to dev environment
    $ zappa deploy dev_api

    # Zappa will creates the API Gateway url for you similar to this
    $ curl https://zzz.execute-api.us-west-2.amazonaws.com/dev_api

## Schedule
    # deploy API to dev environment (doesn't create APIGateway resource)
    $ zappa deploy dev_event

    # schedule CloudWatch to run this Lambda function every minute
    $ zappa schedule dev_event

    # watch log
    $ zappa log dev_event
