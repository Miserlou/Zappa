import logging
from flask import Flask

app = Flask(__name__)
logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

@app.route('/', methods=['GET', 'POST'])
def index():
    logger.info('Lambda function invoked index()')

    return 'hello from Flask!'

if __name__ == '__main__':
    app.run(debug=True)
