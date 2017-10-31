import logging
from flask import Flask, current_app

app = Flask(__name__)
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@app.route('/', methods=['GET', 'POST'])
def lambda_handler(event=None, context=None):
    return current_app.send_static_file('index.html')

@app.route('/static/<string:page_name>', methods=['GET'])
def render_static(page_name):
    return current_app.send_static_file(page_name)

if __name__ == '__main__':
    app.run(debug=True)
