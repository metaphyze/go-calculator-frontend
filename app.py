from flask import Flask, request, jsonify, render_template_string, render_template
import uuid
import sys
import os
import argparse
import requests  # Import the requests library

app = Flask(__name__)


# Read configuration from environment variables
calculation_server_url = os.environ.get('CALCULATION_URL', 'http://localhost:9999')
port = int(os.environ.get('PORT', 5000))


# Serve the webpage
@app.route('/')
def index():
    return render_template('index.html')  # Render the HTML template from the file


# Handle POST request and forward to processing server
@app.route('/submit', methods=['POST'])
def submit_problem():
    data = request.get_json()
    problem = data.get('problem', '')

    # Generate a UUID
    problem_id = str(uuid.uuid4())

    # Prepare the payload for the processing server
    payload = {
        'problem': problem,
        'id': problem_id
    }

    # Forward the request to the processing server
    try:
        response = requests.post(f'{calculation_server_url}/calculate', json=payload)
        response_data = response.json()  

        # Check if the response contains success information
        if response_data.get('success'):
            message = response_data.get('answer', 'No answer returned.')
        else:
            message = f"Error from processing server: {response_data.get('error', 'Unknown error')}"
    except requests.exceptions.RequestException as e:
        message = f'Error forwarding request: {str(e)}'


    # Return the response in JSON format
    return jsonify({'message': message})

if __name__ == '__main__':
    # Set up argument parser to accept command-line arguments
    parser = argparse.ArgumentParser(description="Flask server for problem submission.")
    parser.add_argument('--port', type=int, default=0, help="Port number for the Flask server.")
    parser.add_argument('--calculation-url', type=str, default='', help="URL of the calculation server.")

    args = parser.parse_args()

    if  args.port != 0:
        port = args.port

    if args.calculation_url != '':
        calculation_server_url = args.calculation_url

    app.run(host='0.0.0.0', port=port, debug=True)  # Bind to all interfaces

