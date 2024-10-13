from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import os
import requests
from bson import ObjectId


app = Flask(__name__)

# Read configuration from environment variables
calculation_server_url = os.environ.get('CALCULATION_URL', 'http://localhost:9999')
user_db_host_and_port = os.environ.get('USER_DB_HOST_AND_PORT','localhost:27017')
port = int(os.environ.get('PORT', 5000))

app.secret_key = 'your_secret_key'  # Necessary for session management

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize MongoDB connection
client = MongoClient(f'mongodb://{user_db_host_and_port}/')  # Change as needed for your MongoDB instance
#db = client['users']
db = client.users
users_collection = db.users


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
        print(e)
        return None


# Serve the webpage
@app.route('/', methods=['GET'])
#@app.route('/index', methods=['GET'])
@login_required  # Require login to access the index page
def index():
    return render_template('index.html')


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
            return "Username already exists!"

        # Insert new user into the database
        users_collection.insert_one({"name": username, "password": hashed_password, "email": email})
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

            # Redirect to index page after successful login
            return redirect(url_for('index'))
        return "Invalid username or password!"

    return render_template('login.html')


# Logout route
@app.route('/logout')
@login_required
def logout():
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
    app.run(host='0.0.0.0', port=port, debug=True)
