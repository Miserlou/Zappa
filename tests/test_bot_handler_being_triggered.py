API_STAGE = "dev"
APP_FUNCTION = "app"
APP_MODULE = "tests.test_wsgi_script_name_app"
BINARY_SUPPORT = False
CONTEXT_HEADER_MAPPINGS = {}
DEBUG = "True"
DJANGO_SETTINGS = None
DOMAIN = "api.example.com"
ENVIRONMENT_VARIABLES = {}
LOG_LEVEL = "DEBUG"
PROJECT_NAME = "wsgi_script_name_settings"
COGNITO_TRIGGER_MAPPING = {}
AWS_BOT_EVENT_MAPPING = {
    "intent-name:DialogCodeHook": "tests.test_handler.handle_bot_intent"
}
