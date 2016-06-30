APP_MODULE = 'tests.test_app'
APP_FUNCTION = 'hello_world'
DEBUG = 'True'
LOG_LEVEL = 'DEBUG'
SCRIPT_NAME = 'hello_world'
DOMAIN = None
API_STAGE = 'ttt888'

REMOTE_ENV_BUCKET='lmbda'
REMOTE_ENV_FILE='test_env.json'
## test_env.json
#{
#	"hello": "world"
#}
#

def prebuild_me():
    print("This is a prebuild script!")
