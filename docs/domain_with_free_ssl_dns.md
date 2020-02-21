# Using Let's Encrypt with Zappa

If you want to deploy a Zappa application using a domain or a subdomain, you'll need a valid SSL certificate. Fortunately for you, Zappa provides support for free SSL certificates using [Let's Encrypt](https://letsencrypt.org/) out of the box!

### Step 1: Creating a Hosted Zone

To verify that you own your domain, Let's Encrypt issues a challenge for you to prove that you control your domain's DNS servers. To do this automatically, Zappa requires that you use AWS's [Route 53](https://aws.amazon.com/route53/) DNS service.

In the AWS [Route 53 web console](https://console.aws.amazon.com/route53/), create a new "Hosted Zone" for your domain. Define this value as the _apex_ ("naked") domain of your target domain. (So even if you wanted `test.zappa.io`, call this zone `zappa.io`). This will automatically give you a set of NS servers for your domain to use, like so:

[![Console](http://i.imgur.com/1DflCR4.png)](https://console.aws.amazon.com/route53/)

In your domain registrar's settings, set these new values as your domain's nameservers. These may take up to an hour to propagate.

### Step 2: Generating an AWS Account Key

Next, you'll need to generate an account key that you'll use with Let's Encrypt.

To generate it, simply:

```
$ openssl genrsa 2048 > account.key; 
```

It's very important that you keep that key safe!

_Note that this is a 2048b key. It's generally preferred to use a stronger 4096b key, but at time of writing, AWS did not support keys that large. Use larger keys at your own risk. If you get it working with a 4096b key, please file an issue so that we can update this documentation._

### Step 3: Certification

Finally, configure your `zappa_settings.json` to use this domain and key:

```javascript
{
    "dev": {
    ...
       "domain": "test.zappa.io", // Your target domain
       "lets_encrypt_key": "account.key", // Path to account key
    ...
    }
}
```

If you're doing this as part of a continuous deployment system, you can also store account key in a secure S3 bucket and point to it like so:

```javascript
{
    "dev": {
    ...
       "domain": "test.zappa.io", // Your target domain
       "lets_encrypt_key": "s3://your-secure-bucket/account.key", // S3 Path to account key
    ...
    }
}
```

Then, to verify, create and install your certificate with your domain, simply run the command:

```
$ zappa certify
```

And you're done! You can now use your SSL-secured Zappa application on your target domain.

**Please note** that the first time you run this command, it can take around 45 minutes for Amazon to create your domain, and it'll take about 60 seconds every time after that.

Let's Encrypt certificates only last for 3 months, so make sure that you remember to renew in time.

### Step 4 (Optional): Auto-Renew

If you want your certificates to renew automatically, use simply need to define a `lets_encrypt_expression` in your settings, like so:

```javascript
{
    "dev": {
    ...
       "domain": "test.zappa.io", // Your target domain
       "lets_encrypt_key": "s3://your-secure-bucket/account.key", // S3 Path to account key
       "lets_encrypt_expression": "rate(15 days)", // LE Renew schedule
    ...
    }
}
```

The only caveat with this is that your functions `timeout_seconds` must be greater than `60`, as that's how long it takes the DNS to propagate. The auto-renewer will be installed whenever you next `update` or `schedule`, though you may need to re`deploy` to up your `timeout_seconds`.
