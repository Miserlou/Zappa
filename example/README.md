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
    $ zappa tail dev_event

You can also call a scheduled function packaged along with your normal WSGI app:

    # deploy API to prod environment
    $ zappa deploy prod

    # schedule CloudWatch to run mymodule.myfunc every 5 minutes
    $ zappa schedule prod

This function can optionally take the usual `event` and `context` lambda arguments.
See `mymodule.myfunc_with_events` for an example of this.

## Local Testing

To test locally you can execute the WSGI app like you would normally.

    $ python app.py

You can also call your scheduled function locally. When deployed, the handler will import and run this function.
For example, in "prod" it is defined as "mymodule.myfunc", so it can be called as such:

    $ python -c "import mymodule; mymodule.myfunc()"

If your function uses the events argument you will need to send a dict with what the function expects.
Scheduled events use a structure similar to the following:


```python
{
  "account": "123456789012",
  "region": "us-east-1",
  "detail": {},
  "detail-type": "Scheduled Event",
  "source": "aws.events",
  "time": "1970-01-01T00:00:00Z",
  "id": "cdc73f9d-aea9-11e3-9d5a-835b769c0d9c",
  "resources": [
    "arn:aws:events:us-east-1:123456789012:rule/mymodule.myfunc"
  ]
}
```

If your function is also using the context, check out [mock](https://pypi.python.org/pypi/mock) for help building
an artificial context object.
