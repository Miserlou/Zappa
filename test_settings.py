APP_MODULE = 'tests.test_app'
APP_FUNCTION = 'hello_world'
DJANGO_SETTINGS = None 
DEBUG = 'True'
LOG_LEVEL = 'DEBUG'
SCRIPT_NAME = 'hello_world'
DOMAIN = None
API_STAGE = 'ttt888'
PROJECT_NAME = 'ttt888'

REMOTE_ENV_BUCKET='lmbda'
REMOTE_ENV_FILE='test_env.json'
## test_env.json
#{
#	"hello": "world"
#}
#

def prebuild_me():
    print("This is a prebuild script!")

def callback(self):
    print("this is a callback")

def aws_event(event, contect):
    print("AWS EVENT")

def command():
    print("command")
