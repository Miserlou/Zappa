# Zappa Example

This will deploy a simple Flask app

## Setup
    # configure your AWS keys
    $ aws configure

## Deploy
    # deploy to dev environment
    $ zappa deploy dev

    # Zappa will creates the API Gateway url for you similar to this
    $ curl https://zzz.execute-api.us-west-2.amazonaws.com/dev

## Schedule
    # schedule CloudWatch to run this Lambda function every 5 minutes
    $ zappa schedule dev
