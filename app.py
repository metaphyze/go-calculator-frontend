import logging

from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import os
import requests
import pika
import threading
import json
from bson import ObjectId
from datetime import datetime
from flask import flash

# Configure logging before accessing app.logger
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Read configuration from environment variables
calculation_server_url = os.environ.get('CALCULATION_URL', 'http://localhost:9999')
user_db_host_and_port = os.environ.get('USER_DB_HOST_AND_PORT', 'localhost:27017')
log_db_host_and_port = os.environ.get('LOG_DB_HOST_AND_PORT', 'localhost:27017')
rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'localhost')
rabbitmq_user = os.environ.get('RABBITMQ_USER', 'guest')
rabbitmq_password = os.environ.get('RABBITMQ_PASSWORD', 'guest')

port = int(os.environ.get('PORT', 5000))

app.secret_key = 'your_secret_key'  # Necessary for session management

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize MongoDB connection
userClient = MongoClient(f'mongodb://{user_db_host_and_port}/')
users_collection = userClient.users.users

logClient = MongoClient(f'mongodb://{log_db_host_and_port}/')
events_collection = logClient.user_events.events

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_id, username, email):
        self.id = user_id
        self.username = username
        self.email = email


# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    try:
        user_data = users_collection.find_one({"_id": ObjectId(user_id)})
        if user_data:
            return User(user_id=user_data['_id'], username=user_data['name'], email=user_data['email'])
        return None
    except Exception as e:
        app.logger.error(f"Error loading user: {e}")
        return None


# Function to send messages to RabbitMQ in a separate thread
def send_message(event_type, username, ip_address, target_user=''):
    timestamp = datetime.utcnow().isoformat() + 'Z'
    thread = threading.Thread(target=send_message_thread, args=(event_type, username, timestamp, ip_address,target_user))
    thread.start()

def send_message_thread(event_type, username, timestamp, ip_address,target_user):
    try:
        # Establish connection with RabbitMQ
        credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_password)
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host, credentials=credentials))
        channel = connection.channel()

        # Declare a durable queue
        channel.queue_declare(queue='user_events', durable=True)

        # Prepare message payload
        message = {
            'username': username,
            'event_type': event_type,
            'timestamp': timestamp,  # Use the timestamp passed to this function
            'ip_address': ip_address,  # Add the IP address here
            'target_user': target_user
        }

        # Publish the message to RabbitMQ
        channel.basic_publish(exchange='',
                              routing_key='user_events',
                              body=json.dumps(message).encode('utf-8'),
                              properties=pika.BasicProperties(
                                  delivery_mode=2,  # Make message persistent
                              ))

        connection.close()
        app.logger.info(f"Sent RabbitMQ message: {message}")
    except Exception as e:
        app.logger.error(f"Failed to send message to RabbitMQ: {e}")

# Serve the webpage
@app.route('/', methods=['GET'])
@login_required  # Require login to access the index page
def index():
    return render_template('index.html')

@app.route('/documentation', methods=['GET'])
@login_required  # Require login to access the documentation
def documentation():
    return render_template('documentation.html')

# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Check if user already exists
        if users_collection.find_one({"name": username}):
            return render_template('user_already_exists.html', username=username)

        # Insert new user into the database
        users_collection.insert_one({"name": username, "password": hashed_password, "email": email})

        # Send registration message to RabbitMQ
        send_message('user_created', username, request.remote_addr)

        return redirect(url_for('login'))

    return render_template('register.html')


# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Find user in MongoDB
        user_data = users_collection.find_one({"name": username})
        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_id=user_data['_id'], username=user_data['name'], email=user_data['email'])
            login_user(user)

            # Send login message to RabbitMQ
            send_message('user_logged_in', username, request.remote_addr)

            # Redirect to index page after successful login
            return redirect(url_for('index'))

        # Send failed login attempt message to RabbitMQ
        send_message('failed_login_attempt', username, request.remote_addr)
        return render_template('invalid_login.html')

    return render_template('login.html')


# Logout route
@app.route('/logout')
@login_required
def logout():
    send_message('user_logged_out', current_user.username, request.remote_addr)  # Send logout message
    logout_user()
    return redirect(url_for('login'))


# Handle POST request and forward to processing server (requires login)
@app.route('/submit', methods=['POST'])
@login_required
def submit_problem():
    data = request.get_json()
    problem = data.get('problem', '')

    # Generate a UUID
    problem_id = str(uuid.uuid4())

    # Prepare the payload for the processing server
    payload = {
        'problem': problem,
        'id': problem_id,
        'username': current_user.username  # 'current_user' is provided by Flask-Login
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

@app.route('/manage_users', methods=['GET'])
@login_required
def manage_users():
    if current_user.username != 'admin':  # Check if the logged-in user is not 'admin'
        return redirect(url_for('index'))  # Redirect non-admin users to home page

    # Retrieve all users from the database
    all_users = list(users_collection.find({}, {"name": 1, "email": 1}))  # Only fetch name and email fields

    return render_template('manage_users.html', users=all_users, current_user=current_user.username)


@app.route('/delete_user/<username>', methods=['POST'])
@login_required
def delete_user(username):
    if current_user.username != 'admin':  # Check if the logged-in user is not 'admin'
        send_message('user_deletion_failed_unauthorized', current_user.username, request.remote_addr,
                     username)  # Send logout message

        return redirect(url_for('index'))  # Redirect non-admin users to home page

    if username != current_user.username:
        # Remove the user from the database
        users_collection.delete_one({"name": username})
        send_message('user_deleted', current_user.username, request.remote_addr,username)  # Send logout message
        flash(f'User {username} has been deleted successfully.')
    else:
        send_message('user_deletion_failed_self_deletion', current_user.username, request.remote_addr,
                     username)  # Send logout message
        flash(f'You cannot delete the current logged-in user.')

    return redirect(url_for('manage_users'))

@app.route('/show_logs', methods=['GET'])
@login_required
def show_all_logs():
    if current_user.username != 'admin':
        return redirect(url_for('index'))  # Redirect non-admin users to home page

    # Retrieve all events from the events collection
    events = list(events_collection.find({}).sort("timestamp_ms", 1))  # 1 for ascending order

    return render_template('show_logs.html', events=events)

@app.route('/show_logs/<username>', methods=['GET'])
@login_required
def show_user_logs(username):
    if current_user.username != 'admin':
        return redirect(url_for('index'))  # Redirect non-admin users to home page

    # Retrieve all events for the specified username from the events collection
    events = list(events_collection.find({"username": username}).sort("timestamp_ms", 1))  # 1 for ascending order

    return render_template('show_logs.html', events=events, username=username)


if __name__ == '__main__':
    app.logger.info("Starting server")
    app.run(host='0.0.0.0', port=port, debug=True)
