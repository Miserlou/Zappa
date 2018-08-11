from flask import Flask, request

app = Flask(__name__)


@app.route('/return/request/url', methods=['GET', 'POST'])
def return_request_url():
    return request.url
