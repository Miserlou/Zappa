import os
import unittest

import boto3
import placebo

from zappa.wsgi import create_wsgi_request
from zappa.zappa import Zappa


class TestZappa(unittest.TestCase):
    def get_placebo_session(self):
        session = boto3.Session()
        placebo_dir = os.path.join(os.path.dirname(__file__), 'placebo')
        pill = placebo.attach(session, data_path=placebo_dir)
        pill.playback()
        return session

    ##
    # Sanity Tests
    ##

    def test_test(self):
        self.assertTrue(True)
    ##
    # Basic Tests
    ##

    def test_zappa(self):
        self.assertTrue(True)
        Zappa()

    def test_create_lambda_package(self):
        self.assertTrue(True)
        z = Zappa()
        path = z.create_lambda_zip()
        self.assertTrue(os.path.isfile(path))
        os.remove(path)

    def test_load_credentials(self):
        z = Zappa()

        credentials = '[default]\naws_access_key_id = AK123\naws_secret_access_key = JKL456'
        config = '[default]\noutput = json\nregion = us-east-1'

        credentials_file = open('credentials', 'w')
        credentials_file.write(credentials)
        credentials_file.close()

        config_file = open('config', 'w')
        config_file.write(config)
        config_file.close()

        z.load_credentials('credentials', 'config')

        os.remove('credentials')
        os.remove('config')

        self.assertTrue((z.access_key == "AK123"))
        self.assertTrue((z.secret_key == "JKL456"))
        self.assertTrue((z.aws_region == 'us-east-1'))

    def test_upload_remove_s3(self):
        session = self.get_placebo_session()
        bucket_name = 'test_zappa_upload_s3'
        z = Zappa()
        zip_path = z.create_lambda_zip()
        res = z.upload_to_s3(zip_path, bucket_name, session)
        os.remove(zip_path)
        self.assertTrue(res)
        s3 = session.resource('s3')

        # will throw ClientError with 404 if bucket doesn't exist
        s3.meta.client.head_bucket(Bucket=bucket_name)

        # will throw ClientError with 404 if object doesn't exist
        s3.meta.client.head_object(
            Bucket=bucket_name,
            Key=zip_path,
        )
        res = z.remove_from_s3(zip_path, bucket_name, session)
        self.assertTrue(res)

    def test_create_iam_roles(self):
        session = self.get_placebo_session()
        z = Zappa()
        arn = z.create_iam_roles(session)
        self.assertEqual(arn, "arn:aws:iam::123:role/{}".format(z.role_name))

    ##
    # Logging
    ##

    def test_logging(self):
        """
        TODO
        """
        z = Zappa()

    ##
    # WSGI
    ##

    def test_wsgi_event(self):

        event = {
            "body": {},
            "headers": {
                "Via": "1.1 e604e934e9195aaf3e36195adbcb3e18.cloudfront.net (CloudFront)",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip",
                "CloudFront-Is-SmartTV-Viewer": "false",
                "CloudFront-Forwarded-Proto": "https",
                "X-Forwarded-For": "109.81.209.118, 216.137.58.43",
                "CloudFront-Viewer-Country": "CZ",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "X-Forwarded-Proto": "https",
                "X-Amz-Cf-Id": "LZeP_TZxBgkDt56slNUr_H9CHu1Us5cqhmRSswOh1_3dEGpks5uW-g==",
                "CloudFront-Is-Tablet-Viewer": "false",
                "X-Forwarded-Port": "443",
                "CloudFront-Is-Mobile-Viewer": "false",
                "CloudFront-Is-Desktop-Viewer": "true"
            },
            "params": {
                "parameter_1": "asdf1",
                "parameter_2": "asdf2",
            },
            "method": "GET",
            "query": {
                "dead": "beef"
            }
        }
        request = create_wsgi_request(event)

    def test_wsgi_path_info(self):
        # Test no parameters (site.com/)
        event = {
            "body": {},
            "headers": {},
            "params": {},
            "method": "GET",
            "query": {}
        }

        request = create_wsgi_request(event, trailing_slash=True)
        self.assertEqual("/", request['PATH_INFO'])

        request = create_wsgi_request(event, trailing_slash=False)
        self.assertEqual("/", request['PATH_INFO'])

        # Test parameters (site.com/asdf1/asdf2 or site.com/asdf1/asdf2/)
        event = {
            "body": {},
            "headers": {},
            "params": {
                "parameter_1": "asdf1",
                "parameter_2": "asdf2",
            },
            "method": "GET",
            "query": {}
        }

        request = create_wsgi_request(event, trailing_slash=True)
        self.assertEqual("/asdf1/asdf2/", request['PATH_INFO'])

        request = create_wsgi_request(event, trailing_slash=False)
        self.assertEqual("/asdf1/asdf2", request['PATH_INFO'])


if __name__ == '__main__':
    unittest.main()
