from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_pymongo import PyMongo
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from datetime import datetime, timedelta
import re

app = Flask(__name__)
app.config.from_pyfile('config.py')

# Set a secret key for session management
app.secret_key = '244b39dc516ae585bca489f1263d95a8'  # Use a secure key in production

# Initialize MongoDB
mongo = PyMongo(app)

# Initialize Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # Redirect to login page if unauthorized access

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_id):
        self.id = str(user_id)

# User loader function
@login_manager.user_loader
def load_user(user_id):
    user_data = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if user_data:
        return User(user_data["_id"])
    return None

# Home route that displays tasks and requires login
@app.route('/')
@login_required
def home():
    # Get tasks sorted by priority (high -> medium -> low)
    priority_order = {"high": 1, "medium": 2, "low": 3}
    
    pending_tasks = list(mongo.db.tasks.find(
        {"user_id": current_user.id, "completed": False}
    ).sort([
        ("priority_level", 1),  # Sort by priority
        ("due_date", 1)         # Then by due date
    ]))
    
    completed_tasks = list(mongo.db.tasks.find(
        {"user_id": current_user.id, "completed": True}
    ))
    
    # Calculate statistics
    stats = {
        "total_tasks": len(pending_tasks) + len(completed_tasks),
        "completed_tasks": len(completed_tasks),
        "pending_tasks": len(pending_tasks),
        "completion_rate": round((len(completed_tasks) / (len(pending_tasks) + len(completed_tasks))) * 100 if pending_tasks or completed_tasks else 0, 1),
        "due_today": len([task for task in pending_tasks if task.get('due_date') == datetime.now().strftime('%Y-%m-%d')]),
        "overdue": len([task for task in pending_tasks if task.get('due_date') and task['due_date'] < datetime.now().strftime('%Y-%m-%d')])
    }
    
    # Get tasks due soon for notifications
    upcoming_tasks = [task for task in pending_tasks 
                     if task.get('due_date') and 
                     datetime.strptime(task['due_date'], '%Y-%m-%d') <= datetime.now() + timedelta(days=2)]
    
    return render_template('home.html',
                         pending_tasks=pending_tasks,
                         completed_tasks=completed_tasks,
                         stats=stats,
                         upcoming_tasks=upcoming_tasks)

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('register'))

        # Validate password strength
        if not validate_password(password):
            flash('Password does not meet security requirements!', 'error')
            return redirect(url_for('register'))

        # Check if username exists
        if mongo.db.users.find_one({"username": username}):
            flash('Username already exists!', 'error')
            return redirect(url_for('register'))

        # Create new user
        hashed_password = generate_password_hash(password)
        mongo.db.users.insert_one({
            "username": username,
            "password": hashed_password,
            "created_at": datetime.now()
        })

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

def validate_password(password):
    """
    Validate password strength
    Returns True if password meets all requirements, False otherwise
    """
    if len(password) < 8:
        return False
    
    # Check for at least one uppercase letter
    if not re.search(r'[A-Z]', password):
        return False
    
    # Check for at least one lowercase letter
    if not re.search(r'[a-z]', password):
        return False
    
    # Check for at least one digit
    if not re.search(r'\d', password):
        return False
    
    # Check for at least one special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    
    return True

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_data = mongo.db.users.find_one({"username": username})

        if user_data:
            stored_password = user_data['password']

            # Check if the password is valid
            if check_password_hash(stored_password, password):
                user = User(user_data["_id"])
                login_user(user)  # Log the user in
                flash("Login successful!", "success")
                return redirect(url_for('home'))  # Redirect to home after login
            else:
                flash("Invalid password!", "danger")
        else:
            flash("Invalid username!", "danger")

    return render_template('login.html')

# Route to add a task
@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    priority_levels = {"high": 1, "medium": 2, "low": 3}
    
    new_task = {
        "name": request.form.get('task_name'),
        "description": request.form.get('task_description'),
        "due_date": request.form.get('due_date'),
        "priority": request.form.get('priority'),
        "priority_level": priority_levels.get(request.form.get('priority'), 3),  # For sorting
        "user_id": current_user.id,
        "completed": False,
        "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    mongo.db.tasks.insert_one(new_task)
    flash("Task added successfully!", "success")
    return redirect(url_for('home'))

# Route to mark a task as complete
@app.route('/mark_complete/<task_id>', methods=['POST'])
@login_required
def mark_complete(task_id):
    # Convert string ID to MongoDB ObjectId
    task_id = ObjectId(task_id)
    
    # Update the task
    mongo.db.tasks.update_one(
        {"_id": task_id, "user_id": current_user.id},
        {"$set": {"completed": True}}
    )
    
    flash("Task marked as complete!", "success")
    return redirect(url_for('home'))

# Route to delete a task
@app.route('/delete_task/<task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    # Convert string ID to MongoDB ObjectId
    task_id = ObjectId(task_id)
    
    # Delete the task
    mongo.db.tasks.delete_one({"_id": task_id, "user_id": current_user.id})
    
    flash("Task deleted successfully!", "success")
    return redirect(url_for('home'))

# Logout route
@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/get_notifications')
@login_required
def get_notifications():
    # Get tasks due within the next 2 days
    upcoming_tasks = list(mongo.db.tasks.find({
        "user_id": current_user.id,
        "completed": False,
        "due_date": {
            "$lte": (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
        }
    }))
    
    notifications = []
    for task in upcoming_tasks:
        if task['due_date'] == datetime.now().strftime('%Y-%m-%d'):
            notifications.append({
                "message": f"Task '{task['name']}' is due today!",
                "priority": "high"
            })
        else:
            notifications.append({
                "message": f"Task '{task['name']}' is due soon!",
                "priority": "medium"
            })
    
    return jsonify(notifications)

if __name__ == '__main__':
    app.run(debug=True)