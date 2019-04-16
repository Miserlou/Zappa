from flask import Flask, jsonify

app = Flask(__name__)

API_STAGE = 'dev'
APP_FUNCTION = 'app'
APP_MODULE = 'tests.test_wsgi_script_json'
BINARY_SUPPORT = True
CONTEXT_HEADER_MAPPINGS = {}
DEBUG = 'True'
DJANGO_SETTINGS = None
DOMAIN = 'api.example.com'
ENVIRONMENT_VARIABLES = {}
LOG_LEVEL = 'DEBUG'
PROJECT_NAME = 'wsgi_script_json'
COGNITO_TRIGGER_MAPPING = {}

@app.route('/json', methods=['GET'])
def return_json():
    return jsonify(data="json_data")
