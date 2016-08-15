===================
Zappa Documentation
===================


Serverless Python Web Services
==============================

**Zappa** makes it super easy to deploy all Python WSGI applications on AWS Lambda + API Gateway. Think of it as "serverless" web hosting for your Python web apps.

    *What do you mean "serverless"?*

Okay, so there still is a server - but it only has a 40 millisecond life cycle! Serverless in this case means "**without any permanent infrastucture**."

With a traditional HTTP server, the server is online 24/7, processing requests one by one as they come in. If the queue of incoming requests grows too large, some requests will time out. With Zappa, **each request is given its own virtual HTTP "server"** by Amazon API Gateway. AWS handles the horizontal scaling automatically, so no requests ever time out. Each request then calls your application from a memory cache in AWS Lambda and returns the response via Python's WSGI interface. After your app returns, the "server" dies.

Better still, with Zappa you only pay for the milliseconds of server time that you use, so it's many **orders of magnitude cheaper** than VPS/PaaS hosts like Linode or Heroku - and in most cases, it's completely free. Plus, there's no need to worry about load balancing or keeping servers online ever again.

It's great for deploying serverless microservices with frameworks like Flask and Bottle, and for hosting larger web apps and CMSes with Django. Or, you can use any WSGI-compatible app you like! You **probably don't need to change your existing applications** to use it, and you're not locked into using it.

And finally, Zappa is **super easy to use**. You can deploy your application with a single command out of the box.

Using **Zappa** means:

* **No more** tedious web server configuration!
* **No more** paying for 24/7 server uptime!
* **No more** worrying about load balancing / scalability!
* **No more** worrying about keeping servers online!

**Awesome!**

.. image:: _static/zappa_demo.gif

Contents:

.. toctree::
    :maxdepth: 2

    quickstart
    advanced
    guides
    config
    press
    sites
    hacks
    contrib

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

