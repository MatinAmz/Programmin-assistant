from flask import Flask, Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
import random
from flask_pymongo import PyMongo
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required
from itsdangerous import SignatureExpired
from form import LoginForm, RegistrationForm, ForgotPasswordForm
from bson.objectid import ObjectId
from flask_mail import Mail, Message
import string
import math
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
import bcrypt
from functools import wraps
import subprocess
import tempfile
import os
import traceback
import sys
import datetime
import pytz  # Added for proper timezone handling
from openai import OpenAI
import os
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask_jwt_extended import JWTManager
import io

# Load environment variables from src/.env before anything reads them.
load_dotenv()

app = Flask(__name__)

CORS(app,resources={r"/api/*": {"origins": ["http://localhost:8080","https://understand-ai.org/","https://understand-ai.org/uh/"],"supports_credentials": True}})


app.config['MONGO_DBNAME'] = 'webapp'
app.config['SECRET_KEY'] = os.environ['FLASK_SECRET_KEY']
app.config['MONGO_URI'] = os.environ['MONGO_URI']
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.environ['MAIL_USERNAME']
app.config['MAIL_PASSWORD'] = os.environ['MAIL_PASSWORD']
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

csrf = CSRFProtect(app) 

api_bp = Blueprint('api', __name__)
jwt = JWTManager(app)

csrf.exempt(api_bp)
CORS(api_bp,resources={r"/api/*": {"origins": "http://localhost:8080","supports_credentials": True}})



mail = Mail(app)
# Setup for token generation for password reset
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

mongo = PyMongo(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


def initialize_conversations_collection():
    with app.app_context():
        if 'conversations' not in mongo.db.list_collection_names():
            mongo.db.create_collection('conversations')
            # Indexes for fast queries
            mongo.db.conversations.create_index([('user_id', 1), ('question_id', 1)], unique=True)

initialize_conversations_collection()

def track_activity_start(user_id, activity):
    """Record when a user starts an activity"""
    current_time = datetime.datetime.utcnow()
    
    # Check if there's an existing unfinished activity record
    existing = mongo.db.user_activities.find_one({
        'user_id': user_id,
        'activity': activity,
        'end_time': None  # Unfinished activity
    })
    
    if existing:
        # Update existing record if it exists but wasn't properly closed
        mongo.db.user_activities.update_one(
            {'_id': existing['_id']},
            {'$set': {'start_time': current_time}}
        )
    else:
        # Create new activity record
        mongo.db.user_activities.insert_one({
            'user_id': user_id,
            'activity': activity,
            'start_time': current_time,
            'end_time': None
        })

def track_activity_end(user_id, activity):
    """Record when a user finishes an activity"""
    current_time = datetime.datetime.utcnow()
    
    # Find the most recent unfinished activity for this user and activity
    activity_record = mongo.db.user_activities.find_one(
        {
            'user_id': user_id,
            'activity': activity,
            'end_time': None  # Unfinished activity
        },
        sort=[('start_time', -1)]  # Get the most recent
    )
    
    if activity_record:
        # Calculate duration
        start_time = activity_record['start_time']
        duration_seconds = (current_time - start_time).total_seconds()
        duration_minutes = duration_seconds / 60
        
        # Update the record with end time and duration
        mongo.db.user_activities.update_one(
            {'_id': activity_record['_id']},
            {
                '$set': {
                    'end_time': current_time,
                    'duration_seconds': duration_seconds,
                    'duration_minutes': duration_minutes
                }
            }
        )




# Create users collection
with app.app_context():
   if 'users' not in mongo.db.list_collection_names():
       mongo.db.create_collection('users')

class User(UserMixin):
   def __init__(self, user_data):
       self.id = str(user_data['_id'])
       self.name = user_data['name']
       self.email = user_data['email']
       self.research_group = user_data.get('research_group', 'experiment')  # Updated default


@login_manager.user_loader
def load_user(user_id):
   user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
   return User(user_data) if user_data else None


@app.route('/', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        # Check if email already exists
        existing_user = mongo.db.users.find_one({'email': form.email.data})
        if existing_user:
            flash('Email already exists. Please login.')
            return redirect(url_for('login'))
        
        # Hash the password before storing it
        hashed_password = bcrypt.hashpw(form.password.data.encode('utf-8'), bcrypt.gensalt())
        
        # Save the user to the database
        user = {
            'name': form.name.data,
            'email': form.email.data,
            'password': hashed_password.decode('utf-8')  # Decode to save as string
        }
        result = mongo.db.users.insert_one(user)
        
        # NEW: Assign research group randomly during registration
        inserted_id = result.inserted_id
        group = random.choice(['experiment', 'control'])
        mongo.db.users.update_one(
            {'_id': inserted_id},
            {'$set': {'research_group': group}}
        )
        # Log the assignment (optional, for auditing)
        mongo.db.user_activities.insert_one({
            'user_id': str(inserted_id),
            'activity': 'group_assignment',
            'group': group,
            'timestamp': datetime.datetime.utcnow()
        })
        
        flash('Registration successful!')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html', title='Register', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user_data = mongo.db.users.find_one({'email': form.email.data})
        if user_data and bcrypt.checkpw(form.password.data.encode('utf-8'), user_data['password'].encode('utf-8')):
            # Check if group is assigned; if not, randomize
            if 'research_group' not in user_data or not user_data['research_group']:
                group = random.choice(['experiment', 'control'])
                mongo.db.users.update_one(
                    {'_id': user_data['_id']},
                    {'$set': {'research_group': group}}
                )
                # Log the assignment (optional, for auditing)
                mongo.db.user_activities.insert_one({
                    'user_id': str(user_data['_id']),
                    'activity': 'group_assignment',
                    'group': group,
                    'timestamp': datetime.datetime.utcnow()
                })
            user_obj = User(user_data)
            login_user(user_obj)
            return redirect(url_for('presurvey'))
        flash('Invalid email or password')
    return render_template('auth/login.html', title='Login', form=form)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data
        user = mongo.db.users.find_one({'email': email})

        if user:
            # Generate a random password
            new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))  # Length of 10

            # Hash the new password before storing it
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

            # Update the user's password in the database
            mongo.db.users.update_one({'email': email}, {'$set': {'password': hashed_password.decode('utf-8')}})

            # Send the new password to the user's email
            subject = "Your New Password"
            msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[email])
            msg.body = f"Your new password is: {new_password}\nYou can now log in with this password."
            mail.send(msg)

            flash('A new password has been sent to your email. Please log in with the new password.', 'info')
            return redirect(url_for('login'))
        else:
            flash('Email not found.', 'danger')

    return render_template('auth/forgot_password.html', title='Forgot Password', form=form)

@app.route('/preSurvey', methods=['GET', 'POST'])
@login_required
def presurvey():
    if request.method == 'GET':
        track_activity_start(current_user.id, 'presurvey')
        questions = list(mongo.db.preSurveyQuestion.find())
        return render_template('surveys/preSurvey.html', questions=questions)

    elif request.method == 'POST':
        try:
            print("Form data:", request.form)
            print("Current user:", current_user.id, current_user.name)
            
            user_id = current_user.id
            user_name = current_user.name
            
            questions = list(mongo.db.preSurveyQuestion.find())
            print("Questions from DB:", questions)
            
            answers = {}
            for question in questions:
                key = f"question_{question['_id']}"
                answer = request.form.get(key)
                print(f"Processing {key}: {answer}")
                
                if answer:
                    answers[key] = answer
            
            if len(answers) != len(questions):
                print("Not all questions answered")
                flash("Please answer all questions.", "error")
                return render_template('surveys/preSurvey.html', 
                                    questions=questions, 
                                    answers=answers)
            
            submission = {
                'user_id': user_id,
                'user_name': user_name,
                'answers': answers,
                'submitted_at': datetime.datetime.now(datetime.UTC)
            }
            
            print("Saving submission:", submission)
            mongo.db.preSurveyAnswers.insert_one(submission)
            
            track_activity_end(current_user.id, 'presurvey')
            return redirect(url_for('programming_question', page_num=1))
            
        except Exception as e:
            print("Error in preSurvey:", str(e))
            print("Full error:", traceback.format_exc())
            flash("An error occurred. Please try again.")
            return render_template('surveys/preSurvey.html', 
                                questions=questions)

    return render_template('surveys/preSurvey.html', questions=questions)


def run_code_with_test_cases(code, test_cases):
    results = []
    
    for i, test_case in enumerate(test_cases):
        input_data = test_case.get('input', '')
        expected_output = test_case.get('expected_output', '').strip()
        code_setup = test_case.get('code_setup', '')
        test_name = test_case.get('test_name', f'Test Case {i+1}')
        
        try:
            # Create a temporary file for the test
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                # Start with imports that might be needed
                f.write("import sys\n")
                f.write("import io\n")
                f.write("import asyncio\n\n")
                
                # Write the student's code first
                f.write(code + "\n\n")
                
                # Apply code_setup if provided
                if code_setup:
                    # Handle function replacement cases
                    if code_setup.startswith('def ') or code_setup.startswith('async def '):
                        # Extract function name
                        func_name = code_setup.split('def ')[1].split('(')[0].strip()
                        
                        # Add a modified version of the function that will override the original
                        f.write("# Test function replacement\n")
                        f.write(f"{code_setup}\n\n")
                    else:
                        # Just add the setup code
                        f.write("# Additional test setup\n")
                        f.write(f"{code_setup}\n\n")
                
                # Add general test runner code
                f.write("""
# Test execution wrapper
if __name__ == '__main__':
    # Capture output
    output_capture = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = output_capture
    
    try:
        # Try different execution methods based on what's available
        
        # First check for specific test patterns
        if 'print_flow' in globals():
            # Execute print_flow if it exists (special test case)
            print_flow()
            
        # Check for normal main function
        elif 'main' in globals():
            # Execute main function
            main()
            
        # Look for async functions that might need to be run
        else:
            # Find all async functions
            async_funcs = [name for name, func in globals().items() 
                          if callable(func) and hasattr(func, '__await__')
                          and not name.startswith('__')]
            
            # If we have async functions, run the first one
            if async_funcs:
                asyncio.run(globals()[async_funcs[0]]())
            else:
                # Look for any regular function that might be the main test target
                regular_funcs = [name for name, func in globals().items()
                                if callable(func) and not name.startswith('__') 
                                and not hasattr(func, '__await__')]
                
                # If there's input data and we have a function, try calling it with the input
                if regular_funcs and '""" + input_data + """':
                    # Try to evaluate the input and call the function
                    try:
                        input_val = eval('""" + input_data + """')
                        result = globals()[regular_funcs[0]](input_val)
                        if result is not None:
                            print(result)
                    except:
                        # If eval fails, just call without args
                        result = globals()[regular_funcs[0]]()
                        if result is not None:
                            print(result)
                elif regular_funcs:
                    # Just call the first function without args
                    result = globals()[regular_funcs[0]]()
                    if result is not None:
                        print(result)
    
    except Exception as e:
        # Print exception but continue to capture it
        print(f"Error: {str(e)}")
    
    # Restore stdout and get output
    sys.stdout = original_stdout
    print(output_capture.getvalue().strip())
""")
                
                temp_file = f.name
            
            # Run the test file as a separate process
            process = subprocess.Popen(
                ['python3', temp_file],
                stdin=subprocess.PIPE if input_data else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Get the results with timeout protection
            try:
                stdout, stderr = process.communicate(input=input_data if input_data else None, timeout=10)
                
                # Process the output for special cases
                actual_output = stdout.strip()
                error_msg = stderr.strip()
                
                # Determine if the test passed
                if expected_output.startswith('[') and expected_output.endswith(']'):
                    # Try to compare as Python objects for lists
                    try:
                        expected_list = eval(expected_output)
                        # Try to evaluate actual output as a list
                        if actual_output.startswith('[') and actual_output.endswith(']'):
                            actual_list = eval(actual_output)
                            status = 'passed' if actual_list == expected_list else 'failed'
                        else:
                            status = 'failed'
                    except:
                        # Fall back to string comparison
                        status = 'passed' if actual_output == expected_output else 'failed'
                else:
                    # For non-list outputs, normalize and compare
                    expected_norm = ' '.join(expected_output.split())
                    actual_norm = ' '.join(actual_output.split())
                    status = 'passed' if actual_norm == expected_norm else 'failed'
                
                # Check for errors
                if error_msg and "Traceback" in error_msg:
                    if "RuntimeWarning" not in error_msg:  # Ignore runtime warnings
                        status = 'error'
                
                # Create the result
                result = {
                    'test_name': test_name,
                    'input': input_data,
                    'expected': expected_output,
                    'actual': actual_output,
                    'status': status
                }
                
                if error_msg and "RuntimeWarning" not in error_msg:
                    result['error'] = error_msg
                
                results.append(result)
                
            except subprocess.TimeoutExpired:
                process.kill()
                results.append({
                    'test_name': test_name,
                    'status': 'error',
                    'error': 'Code execution timed out (10 seconds)',
                    'input': input_data
                })
                
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)
                
        except Exception as e:
            import traceback
            results.append({
                'test_name': test_name,
                'status': 'error',
                'error': f'Test runner error: {str(e)}',
                'traceback': traceback.format_exc()
            })
    
    # Ensure we return something even if all tests fail to run
    if not results:
        results.append({
            'test_name': 'System Error',
            'status': 'error',
            'error': 'No test results were generated. The test system may be misconfigured.',
            'actual': '',
            'expected': ''
        })
    
    return results

@app.route('/programming/<page_num>/autosave', methods=['POST'])
@login_required
def autosave_code(page_num):
    try:
        code = request.json.get('code')
        current_time = datetime.datetime.utcnow()
        
        # Create a new document for each autosave to maintain history
        autosave_doc = {
            'user_id': current_user.id,
            'question_id': f'programming_q{page_num}',
            'code': code,
            'saved_at': current_time
        }
        
        # Insert a new document for each autosave
        mongo.db.code_autosaves.insert_one(autosave_doc)
        
        # Don't update any "latest" collection since we don't want to retrieve this code
        
        return jsonify({'status': 'success', 'message': 'Code auto-saved'})
    except Exception as e:
        print(f"Autosave error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    

@app.route('/programming/<page_num>')
@login_required
def programming_question(page_num):
    try:
        # Format the question_id consistently
        question_id = f'programming_q{page_num}'
        
        # Track activity start with try/except to ensure it doesn't break the page
        try:
            track_activity_start(current_user.id, question_id)
        except Exception as tracking_error:
            print(f"Error tracking activity start: {tracking_error}")
            # Continue with the page even if tracking fails
        
        # Get the question from MongoDB using question_id format
        question = mongo.db.programmingQuestions.find_one({'question_id': question_id})
        print(f"Found question: {question}")  # Debug print
        
        if not question:
            print(f"No question found for {question_id}")
            flash('Programming question not found.', 'error')
            return render_template('programming/programming.html',
                            question={'question_text': 'Question not found'},
                            code='',
                            page_num=page_num)
        
        # First try to get autosaved code
        autosaved = mongo.db.code_autosaves.find_one({
            'user_id': current_user.id,
            'question_id': question_id
        }, sort=[('saved_at', -1)])  # Get the most recent autosave
        
        # If no autosave exists, try to get submitted code
        if not autosaved:
            submitted = mongo.db.submissions.find_one({
                'user_id': current_user.id,
                'question_id': question_id
            })
            # If there's submitted code, use it; otherwise, use starter_code from question
            if submitted and submitted.get('code'):
                code = submitted.get('code')
            else:
                # Use the starter code from the question document
                code = question.get('starter_code', '')
        else:
            code = autosaved.get('code')
        
        # Add timer duration to the template context (in minutes)
        # You can customize timer duration per question
        if page_num == '1':
            timer_duration = 20  # 20 minutes for question 1
        elif page_num == '2':
            timer_duration = 30  # 30 minutes for question 2
        else:
            timer_duration = 30  # Default is 30 minutes
        
        # Check user's research group and render appropriate template
        group = getattr(current_user, 'research_group', 'experiment')  # Default to experiment if not set
        if group == 'control':
            # Control group: Custom SRL prompts (hardcoded example; you can fetch from DB)
            srl_prompts = [
                "What is your learning goal for this programming task?",
                "How do you plan to approach solving this problem?",
                "What strategies will you use to test and debug your code?",
                "Reflect on any errors: What caused them and how can you fix them?",
                "How does this task relate to what you've learned before?"
            ]
            # Render SRL-specific template (create this template without AI features)
            return render_template('programming/programming_srl.html',
                                   question=question,
                                   code=code,
                                   page_num=page_num,
                                   timer_duration=timer_duration,
                                   srl_prompts=srl_prompts)  # Pass SRL prompts to template
        else:
            # Experiment group: Standard AI-assisted template
            return render_template('programming/programming.html',
                                   question=question,
                                   code=code,
                                   page_num=page_num,
                                   timer_duration=timer_duration)  # Pass timer duration to template
                          
    except Exception as e:
        print(f"Error in programming_question: {str(e)}")
        traceback.print_exc()
        flash('Error loading programming question', 'error')
        return render_template('programming/programming.html',
                          question={'question_text': 'Error loading question'},
                          code='',
                          page_num=page_num)
    
# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def format_test_results(test_results):
    """Helper to format test results as a readable string."""
    if not test_results:
        return "No test results available."
    formatted = ""
    for result in test_results:
        formatted += f"Test: {result.get('test_name', 'Unknown')}\n"
        formatted += f"Status: {result.get('status', 'Unknown')}\n"
        formatted += f"Input: {result.get('input', '')}\n"
        formatted += f"Expected: {result.get('expected', '')}\n"
        formatted += f"Actual: {result.get('actual', '')}\n"
        if 'error' in result:
            formatted += f"Error: {result['error']}\n"
        formatted += "\n"
    return formatted

@app.route('/programming/<page_num>/prompt', methods=['POST'])
@login_required
def programming_prompt(page_num):
    prompt = request.form.get('prompt')
    code = request.form.get('code', '')

    group = getattr(current_user, 'research_group', 'experiment')
    if group == 'control':
        # log reflection and bail (no AI)
        mongo.db.reflections.insert_one({
            'user_id': current_user.id,
            'question_id': f'programming_q{page_num}',
            'prompt': prompt,
            'timestamp': datetime.datetime.utcnow()
        })
        flash('AI assistance is not available in your group.', 'warning')
        return redirect(url_for('programming_question', page_num=page_num))
    try:
        question_id = f'programming_q{page_num}'
        question = mongo.db.programmingQuestions.find_one({'question_id': question_id})
        question_text = question.get('question_text', 'No question text available.') if question else 'No question text available.'
        
        latest_run = mongo.db.run_attempts.find_one(
            {'user_id': current_user.id, 'question_id': question_id},
            sort=[('timestamp', -1)]
        )
        latest_test_results = ""
        if latest_run:
            if 'test_results' in latest_run:
                latest_test_results = format_test_results(latest_run['test_results'])
            elif 'output' in latest_run:
                latest_test_results = latest_run['output']

        # NEW: Load or initialize conversation history
        conversation = mongo.db.conversations.find_one({
            'user_id': current_user.id,
            'question_id': question_id
        })
        history = conversation.get('history', []) if conversation else []

        # Construct system content (always first in messages)
        system_content = (
            f"You are a helpful programming assistant. "
            f"The programming task is: {question_text}\n"
            f"Current code in editor: {code}\n"
            f"Latest terminal outputs/test results: {latest_test_results or 'No previous runs.'}"
        )

        # Build messages: system + history + new user prompt
        messages = [
            {"role": "system", "content": system_content}
        ] + history + [
            {"role": "user", "content": prompt}
        ]

        # Send to ChatGPT with full history
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        # NEW: Append new user prompt and AI response to history
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": ai_response})

        # Save/upsert updated history
        mongo.db.conversations.update_one(
            {'user_id': current_user.id, 'question_id': question_id},
            {'$set': {'history': history}},
            upsert=True
        )
        
        # Log the interaction (optional, keep as-is)
        mongo.db.ai_interactions.insert_one({
            'user_id': current_user.id,
            'question_id': question_id,
            'prompt': prompt,
            'ai_response': ai_response,
            'timestamp': datetime.datetime.utcnow()
        })
        
    except Exception as e:
        ai_response = f"Error: {str(e)}"
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return ai_response
    
    question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
    return render_template('programming/programming.html',
                         question=question,
                         code=code,
                         page_num=page_num,
                         ai_response=ai_response,
                         prompt=prompt)


@app.route('/programming/<page_num>/run', methods=['POST'])
@login_required
def programming_run(page_num):
    code = request.form.get('code')
    question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
    
    # Get test cases from the question
    test_cases = question.get('test_cases', [])
    
    # Use the improved test case runner
    test_results = run_code_with_test_cases(code, test_cases)
    
    # Log the run attempt
    mongo.db.run_attempts.insert_one({
        'user_id': current_user.id,
        'question_id': f'programming_q{page_num}',
        'code': code,
        'test_results': test_results,
        'timestamp': datetime.datetime.utcnow()
    })
    
    # Return to the same page with test results
    return render_template('programming/programming.html',
                         question=question,
                         code=code,
                         page_num=page_num,
                         test_results=test_results)

@app.route('/programming/<page_num>/submit', methods=['POST'])
@login_required
def programming_submit(page_num):
    print(f"Received submission for page {page_num}")
    try:
        code = request.form.get('code')
        question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
        
        if not question:
            flash('Question not found', 'error')
            return redirect(url_for('programming_question', page_num=page_num))
        
        # Run final tests
        test_cases = question.get('test_cases', [])
        test_results = run_code_with_test_cases(code, test_cases)
        
        # Calculate score
        total_tests = len(test_results)
        passed_tests = sum(1 for result in test_results if result['status'] == 'passed')
        score = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        # Save submission
        submission = {
            'user_id': current_user.id,
            'question_id': f'programming_q{page_num}',
            'code': code,
            'test_results': test_results,
            'score': score,
            'timestamp': datetime.datetime.now(datetime.UTC)
        }
        
        # Save to MongoDB using upsert
        mongo.db.submissions.update_one(
            {
                'user_id': current_user.id,
                'question_id': f'programming_q{page_num}'
            },
            {'$set': submission},
            upsert=True
        )
        
        track_activity_end(current_user.id, f'programming_q{page_num}')
        
        # Updated: No feedback; redirect based on page_num
        if page_num == '1':
            return redirect(url_for('programming_question', page_num='2'))
        elif page_num == '2':
            return redirect(url_for('postsurvey'))
        else:
            flash('Submission complete.', 'success')
            return redirect(url_for('programming_question', page_num=page_num))
        
    except Exception as e:
        print("Error in submit:", str(e))
        traceback.print_exc()
        flash('Error submitting solution', 'error')
        
        # Updated: No feedback; redirect based on page_num even on error
        if page_num == '1':
            return redirect(url_for('programming_question', page_num='2'))
        elif page_num == '2':
            return redirect(url_for('postsurvey'))
        else:
            return redirect(url_for('programming_question', page_num=page_num))

# (Feedback route removed as per request)

@app.route('/postSurvey', methods=['GET', 'POST'])
@login_required
def postsurvey():
    if request.method == 'GET':
        track_activity_start(current_user.id, 'postsurvey')
        questions = list(mongo.db.postSurveyQuestion.find())
        return render_template('surveys/postSurvey.html', questions=questions)
    
    elif request.method == 'POST':
        try:
            print("Form data:", request.form)
            print("Current user:", current_user.id, current_user.name)
            
            user_id = current_user.id
            user_name = current_user.name
            
            questions = list(mongo.db.postSurveyQuestion.find())
            print("Questions from DB:", questions)
            
            answers = {}
            for question in questions:
                key = f"question_{question['_id']}"
                answer = request.form.get(key)
                print(f"Processing {key}: {answer}")
                
                if answer:
                    answers[key] = answer
            
            if len(answers) != len(questions):
                print("Not all questions answered")
                flash("Please answer all questions.", "error")
                return render_template('surveys/postSurvey.html',
                                      questions=questions,
                                      answers=answers)
            
            submission = {
                'user_id': user_id,
                'user_name': user_name,
                'answers': answers,
                'submitted_at': datetime.datetime.now(datetime.UTC)
            }
            
            mongo.db.postSurveyAnswers.insert_one(submission)
            track_activity_end(current_user.id, 'postsurvey')
            # Update user status to indicate completion of the entire process
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {'completed': True, 'completion_date': datetime.datetime.now(datetime.UTC)}}
            )
            
            flash("Thank you for completing the survey! Your participation has been recorded.")
            return redirect(url_for('completion_page'))  # Final thank you/completion page
            
        except Exception as e:
            print("Error in postSurvey:", str(e))
            print("Full error:", traceback.format_exc())
            flash("An error occurred. Please try again.")
            return render_template('surveys/postSurvey.html',
                                  questions=questions)
    
    return render_template('surveys/postSurvey.html', questions=questions)

@app.route('/completion')
@login_required
def completion_page():
    return render_template('completion.html', 
                          user_name=current_user.name,
                          now=datetime.datetime.now())




@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        'status': 'error',
        'message': 'Token has expired'
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({
        'status': 'error',
        'message': 'Invalid token'
    }), 401

@jwt.unauthorized_loader
def unauthorized_callback(error):
    return jsonify({
        'status': 'error',
        'message': 'Missing authorization token'
    }), 401

# Add this route to your blueprint
@api_bp.route('/check-token', methods=['GET'])
@jwt_required()
def check_token():
    # If we get here, the token is valid
    # Optional: Add user details if needed
    current_user_id = get_jwt_identity()
    return jsonify({
        'status': 'success',
        'message': 'Token is valid',
        'user_id': current_user_id
    }), 200

def _insert_login_log(email, user_id):
    """
    Helper to insert a login log for `email`. Uses a global counter
    'login_sequence' in login_logs collection.
    """
    # Find the document with the highest existing login_sequence
    last_log = mongo.db.login_logs.find_one(sort=[("login_sequence", -1)])
    if last_log and "login_sequence" in last_log:
        next_sequence = last_log["login_sequence"] + 1
    else:
        next_sequence = 1

    # Current time in US Central / America/Chicago via pytz
    now_central = datetime.datetime.now(pytz.timezone('America/Chicago'))

    # Build and insert the login_log
    login_log = {
        "user_id": user_id,
        "email": email,
        "login_sequence": next_sequence,
        "time": now_central
    }
    mongo.db.login_logs.insert_one(login_log)

@api_bp.route('/microsoft_login', methods=['POST'])
def microsoft_login():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No input data provided"}), 400

    email = data.get("email", "").lower()
    name = data.get("name")
    if not email or not name:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    # find-or-create
    existing_user = mongo.db.users.find_one({"email": email})
    if existing_user:
        user_id = str(existing_user["_id"])
    else:
        import uuid
        random_password = str(uuid.uuid4())
        hashed_password = bcrypt.hashpw(random_password.encode("utf-8"), bcrypt.gensalt())
        new_user = {
            "name": name,
            "email": email,
            "password": hashed_password.decode("utf-8"),
        }
        result = mongo.db.users.insert_one(new_user)
        user_id = str(result.inserted_id)

    # Check and assign research group if not set (randomization)
    try:
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        if 'research_group' not in user_data or not user_data['research_group']:
            group = random.choice(['experiment', 'control'])
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {'research_group': group}}
            )
            # Log the assignment for auditing
            mongo.db.user_activities.insert_one({
                'user_id': user_id,
                'activity': 'group_assignment',
                'group': group,
                'timestamp': datetime.datetime.utcnow()
            })
    except Exception as e:
        print(f"Error assigning research group: {str(e)}")
        # Continue even if assignment fails (you can add error response if needed)

    # log it
    _insert_login_log(email, user_id)

    # create JWT
    access_token = create_access_token(identity=user_id, expires_delta=datetime.timedelta(hours=1))

    # --- check previous submissions ---
    presurvey_submitted = mongo.db.preSurveyAnswers.find_one(
        {'user_id': user_id}
    ) is not None

    pq1_submitted = mongo.db.submissions.find_one(
        {'user_id': user_id, 'question_id': 'programming_q1'}
    ) is not None

    pq2_submitted = mongo.db.submissions.find_one(
        {'user_id': user_id, 'question_id': 'programming_q2'}
    ) is not None

    return jsonify({
        "status": "success",
        "message": "Microsoft login successful!",
        "access_token": access_token,
        "user": {"id": user_id, "name": name, "email": email},
        "presurvey_submitted": presurvey_submitted,
        "programming_q1_submitted": pq1_submitted,
        "programming_q2_submitted": pq2_submitted
    })

@api_bp.route('/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No input data provided"}), 400

    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"status": "error", "message": "Missing email or password"}), 400

    user = mongo.db.users.find_one({"email": email})
    if user and bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
        user_id = str(user["_id"])

        # Check and assign research group if not set (randomization)
        try:
            user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if 'research_group' not in user_data or not user_data['research_group']:
                group = random.choice(['experiment', 'control'])
                mongo.db.users.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$set': {'research_group': group}}
                )
                # Log the assignment for auditing
                mongo.db.user_activities.insert_one({
                    'user_id': user_id,
                    'activity': 'group_assignment',
                    'group': group,
                    'timestamp': datetime.datetime.utcnow()
                })
        except Exception as e:
            print(f"Error assigning research group: {str(e)}")
            # Continue even if assignment fails (you can add error response if needed)

        # log the login
        _insert_login_log(email, user_id)

        # create JWT
        access_token = create_access_token(identity=user_id, expires_delta=datetime.timedelta(days=1))

        # --- check previous submissions ---
        presurvey_submitted = mongo.db.preSurveyAnswers.find_one(
            {'user_id': user_id}
        ) is not None

        pq1_submitted = mongo.db.submissions.find_one(
            {'user_id': user_id, 'question_id': 'programming_q1'}
        ) is not None

        pq2_submitted = mongo.db.submissions.find_one(
            {'user_id': user_id, 'question_id': 'programming_q2'}
        ) is not None

        return jsonify({
            "status": "success",
            "message": "Login successful!",
            "access_token": access_token,
            "user": {
                "id": user_id,
                "name": user.get("name"),
                "email": user.get("email"),
                'research_group': user.get('research_group', 'experiment')
            },
            "presurvey_submitted": presurvey_submitted,
            "programming_q1_submitted": pq1_submitted,
            "programming_q2_submitted": pq2_submitted
        })
    else:
        return jsonify({"status": "error", "message": "Invalid email or password"}), 401


@api_bp.route('/register', methods=['POST'])
def api_register():
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No input data provided'}), 400

    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    if not name or not email or not password:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    existing_user = mongo.db.users.find_one({'email': email})
    if existing_user:
        return jsonify({'status': 'error', 'message': 'Email already exists. Please login.'}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    user = {
        'name': name,
        'email': email,
        'password': hashed_password.decode('utf-8')
    }
    result = mongo.db.users.insert_one(user)
    new_user = mongo.db.users.find_one({'_id': result.inserted_id})

    # NEW: Assign research group randomly during registration
    group = random.choice(['experiment', 'control'])
    mongo.db.users.update_one(
        {'_id': result.inserted_id},
        {'$set': {'research_group': group}}
    )
    # Log the assignment
    mongo.db.user_activities.insert_one({
        'user_id': str(result.inserted_id),
        'activity': 'group_assignment',
        'group': group,
        'timestamp': datetime.datetime.utcnow()
    })

    return jsonify({
        'status': 'success',
        'message': 'Registration successful!',
        'user': {
            'id': str(new_user['_id']),
            'name': new_user['name'],
            'email': new_user['email'],
            'research_group': group 
        }
    }), 201


@api_bp.route('/forgot-password', methods=['POST'])
def api_forgot_password():
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No input data provided'}), 400
    
    email = data.get('email')
    if not email:
        return jsonify({'status': 'error', 'message': 'Email is required'}), 400
    
    user = mongo.db.users.find_one({'email': email})
    if not user:
        return jsonify({'status': 'error', 'message': 'Email not found'}), 404
    
    # Generate a new password
    new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Update user's password
    mongo.db.users.update_one(
        {'email': email},
        {'$set': {'password': hashed_password}}
    )
    
    # Send email with new password
    msg = Message("Your New Password", 
                  sender=app.config['MAIL_USERNAME'], 
                  recipients=[email])
    msg.body = f"Your new password is: {new_password}"
    mail.send(msg)
    
    return jsonify({'status': 'success', 'message': 'New password sent to your email'})

    
@api_bp.route('/presurvey', methods=['GET', 'POST'])
@jwt_required()
def api_presurvey():
    current_user_id = get_jwt_identity()  # This retrieves the user identity stored in the token    
    if request.method == 'GET':
        track_activity_start(current_user_id, 'presurvey')
        questions = list(mongo.db.preSurveyQuestion.find({}, {'_id': 0}))
        return jsonify({'questions': questions})
    
    elif request.method == 'POST':
        data = request.get_json()
        if not data or 'answers' not in data:
            return jsonify({'status': 'error', 'message': 'Invalid data format'}), 400
        
        submission = {
            'user_id': current_user_id,
            'answers': data['answers'],
            'submitted_at': datetime.datetime.now(datetime.UTC)
        }
        
        mongo.db.preSurveyAnswers.insert_one(submission)
        track_activity_end(current_user_id, 'presurvey')
        
        return jsonify({'status': 'success', 'message': 'Survey submitted successfully'})

# autosave code endpoint updated for JWT
@api_bp.route('/autosave/<page_num>', methods=['POST'])
@jwt_required()
def api_autosave_code(page_num):
    data = request.get_json()
    code = data.get('code', '')
    try:
        user_id = get_jwt_identity()
        current_time = datetime.datetime.utcnow()
        autosave_doc = {
            'user_id': user_id,
            'question_id': f'programming_q{page_num}',
            'code': code,
            'saved_at': current_time
        }
        mongo.db.code_autosaves.insert_one(autosave_doc)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# programming question endpoint updated for JWT
@api_bp.route('/question/<page_num>', methods=['GET'])
@jwt_required()
def api_programming_question(page_num):
    try:
        question = mongo.db.programmingQuestions.find_one(
            {'question_id': f'programming_q{page_num}'},
            {'_id': 0, 'question_id': 1, 'question_text': 1, 'test_cases': 1}
        )
        if not question:
            return jsonify({'status': 'error', 'message': 'Question not found'}), 404
        
        # Convert ObjectId fields in test cases if they exist
        if 'test_cases' in question:
            for tc in question['test_cases']:
                if '_id' in tc:
                    tc['_id'] = str(tc['_id'])
                    
        return jsonify({
            'status': 'success',
            'question': question
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# New routes
@api_bp.route('/programming/<page_num>/autosave', methods=['POST'])
@jwt_required()
def autosave_code(page_num):
    try:
        code = request.json.get('code')
        current_time = datetime.datetime.utcnow()
        current_user_id = get_jwt_identity()
        
        autosave_doc = {
            'user_id': current_user_id,
            'question_id': f'programming_q{page_num}',
            'code': code,
            'saved_at': current_time
        }
        
        mongo.db.code_autosaves.insert_one(autosave_doc)
        
        return jsonify({'status': 'success', 'message': 'Code auto-saved'})
    except Exception as e:
        print(f"Autosave error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/programming/<page_num>', methods=['GET'])
@jwt_required()
def programming_question(page_num):
    try:
        current_user_id = get_jwt_identity()
        user_data = mongo.db.users.find_one({'_id': ObjectId(current_user_id)})
        group = user_data.get('research_group', 'experiment')  # Fetch from DB
        
        question_id = f'programming_q{page_num}'
        
        # Track activity start (errors are caught and logged)
        try:
            track_activity_start(current_user_id, question_id)
        except Exception as tracking_error:
            print(f"Error tracking activity start: {tracking_error}")
        
        # Retrieve the question from MongoDB
        question = mongo.db.programmingQuestions.find_one({'question_id': question_id})
        if not question:
            return jsonify({'status': 'error', 'message': 'Programming question not found.'}), 404
        
        # Check for autosaved code first, then submitted code, then fallback to starter code
        autosaved = mongo.db.code_autosaves.find_one({
            'user_id': current_user_id,
            'question_id': question_id
        }, sort=[('saved_at', -1)])
        
        if not autosaved:
            submitted = mongo.db.submissions.find_one({
                'user_id': current_user_id,
                'question_id': question_id
            })
            if submitted and submitted.get('code'):
                code = submitted.get('code')
            else:
                code = question.get('starter_code', '')
        else:
            code = autosaved.get('code')
        
        # Set timer duration based on page number
        if page_num == '1':
            timer_duration = 20  # 20 minutes for question 1
        elif page_num == '2':
            timer_duration = 30  # 30 minutes for question 2
        else:
            timer_duration = 30  # Default is 30 minutes
        
        response = {
            'status': 'success',
            'question': question,
            'code': code,
            'page_num': page_num,
            'timer_duration': timer_duration,
            'ai_mode': 'free' if group == 'control' else 'srl'
        }
        
        if group == 'experiment':
            # Provide SRL prompts for control group
            srl_prompts = [
                "What is your learning goal for this programming task?",
                "How do you plan to approach solving this problem?",
                "What strategies will you use to test and debug your code?",
                "Reflect on any errors: What caused them and how can you fix them?",
                "How does this task relate to what you've learned before?"
            ]  # Or fetch from DB
            response['srl_prompts'] = srl_prompts
        
        return jsonify(response)
    except Exception as e:
        print(f"Error in programming_question: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Error loading programming question'}), 500

@api_bp.route('/programming/<page_num>/prompt', methods=['POST'])
@jwt_required()
def programming_prompt(page_num):
    current_user_id = get_jwt_identity()
    user_data = mongo.db.users.find_one({'_id': ObjectId(current_user_id)})
    group = user_data.get('research_group', 'experiment')

    data = request.get_json()
    prompt = data.get('prompt')
    code = data.get('code', '')

    if not prompt:
        return jsonify({'status': 'error', 'message': 'Prompt is required'}), 400

    try:
        question_id = f'programming_q{page_num}'
        question = mongo.db.programmingQuestions.find_one({'question_id': question_id})
        question_text = question.get('question_text', 'No question text available.') if question else 'No question text available.'

        latest_run = mongo.db.run_attempts.find_one(
            {'user_id': current_user_id, 'question_id': question_id},
            sort=[('timestamp', -1)]
        )
        latest_test_results = ""
        if latest_run:
            if 'test_results' in latest_run:
                latest_test_results = format_test_results(latest_run['test_results'])
            elif 'output' in latest_run:
                latest_test_results = latest_run['output']

        # Load or initialize conversation history
        conversation = mongo.db.conversations.find_one({
            'user_id': current_user_id,
            'question_id': question_id
        })
        history = conversation.get('history', []) if conversation else []

        # ----- Different system prompts depending on group -----
        if group == 'control':
            # Free AI assistant mode
            system_content = (
                f"You are a helpful programming assistant.\n"
                f"Programming task: {question_text}\n"
                f"Current code in editor: {code}\n"
                f"Latest terminal outputs/test results: {latest_test_results or 'No previous runs.'}"
            )
            user_message = prompt
        else:
            # SRL (planning / monitoring / reflection) mode
            system_content = (
                f"You are a programming learning companion.\n"
                f"Student is solving: {question_text}\n"
                f"Current code: {code}\n"
                f"Latest results: {latest_test_results or 'No previous runs.'}\n\n"
                f"Encourage self-regulated learning (planning, monitoring, reflection)."
            )
            user_message = f"Student reflection: {prompt}"

        # Build messages
        messages = [{"role": "system", "content": system_content}] + history + [{"role": "user", "content": user_message}]

        # Call OpenAI
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.7
        )
        ai_response = response.choices[0].message.content

        # Update history
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": ai_response})
        mongo.db.conversations.update_one(
            {'user_id': current_user_id, 'question_id': question_id},
            {'$set': {'history': history}},
            upsert=True
        )

        # Log interaction
        mongo.db.ai_interactions.insert_one({
            'user_id': current_user_id,
            'question_id': question_id,
            'group': group,
            'prompt': prompt,
            'ai_response': ai_response,
            'timestamp': datetime.datetime.utcnow()
        })

    except Exception as e:
        ai_response = f"Error: {str(e)}"

    return jsonify({
        'question_id': f'programming_q{page_num}',
        'prompt': prompt,
        'code': code,
        'ai_response': ai_response
    })



@api_bp.route('/programming/<page_num>/run', methods=['POST'])
@jwt_required()
def programming_run(page_num):
    current_user_id = get_jwt_identity()
    data = request.get_json()  
    code = data.get('code')
 
    if not code:
        return jsonify({'status': 'error', 'message': 'Code is required'}), 400
 
    question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
    if not question:
        return jsonify({'status': 'error', 'message': 'Question not found'}), 404
 
    # Run the user-submitted code
    output = run_code_simple(code)
 
    # Save the code and output to MongoDB
    mongo.db.run_attempts.insert_one({
        'user_id': current_user_id,
        'question_id': f'programming_q{page_num}',
        'code': code,
        'output': output,
        'timestamp': datetime.datetime.utcnow()
    })
 
    # Return response with output
    return jsonify({
        'status': 'success',
        'question': {
            'title': question.get('title'),
            'description': question.get('description'),
            'question_id': question.get('question_id')
        },
        'code': code,
        'output': output,
        'page_num': page_num
    })
 
 
# Modified programming submit route with login_sequence check
@api_bp.route('/programming/<page_num>/submit', methods=['POST'])
@jwt_required()
def programming_submit(page_num):
    current_user_id = get_jwt_identity()
    data = request.get_json()  # Expecting JSON body with key 'code'
    code = data.get('code')

    if not code:
        return jsonify({'status': 'error', 'message': 'No code provided'}), 400

    question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
    if not question:
        return jsonify({'status': 'error', 'message': 'Question not found'}), 404

    # Run tests and calculate score
    test_cases = question.get('test_cases', [])
    test_results = run_code_with_test_cases(code, test_cases)
    total_tests = len(test_results)
    passed_tests = sum(1 for result in test_results if result.get('status') == 'passed')
    score = (passed_tests / total_tests) * 100 if total_tests > 0 else 0

    submission = {
        'user_id': current_user_id,
        'question_id': f'programming_q{page_num}',
        'code': code,
        'test_results': test_results,
        'score': score,
        'timestamp': datetime.datetime.now(datetime.timezone.utc)
    }

    # Save submission using upsert
    mongo.db.submissions.update_one(
        {
            'user_id': current_user_id,
            'question_id': f'programming_q{page_num}'
        },
        {'$set': submission},
        upsert=True
    )

    track_activity_end(current_user_id, f'programming_q{page_num}')

    # Fetch the most recent login_log for this user
    last_log = mongo.db.login_logs.find_one(
        {'user_id': current_user_id},
        sort=[('login_sequence', -1)]
    )

    if last_log and (last_log['login_sequence'] % 2 == 1):
        # If login_sequence is odd, direct to programming question 2
        return jsonify({
            'status': 'success',
            'message': 'Submission saved. Please proceed to programming question 2.'
        })

    # Otherwise, use the existing page-based logic (updated: no feedback mention)
    if page_num == '2':
        return jsonify({'status': 'success', 'message': 'Submission saved. Please proceed to postsurvey.'})
    else:
        return jsonify({'status': 'success', 'message': 'Submission saved. Proceed to next question.'})
    

@app.route('/debug/conversations/<user_id>/<question_id>', methods=['GET'])
@login_required  
def debug_conversations(user_id, question_id):
    conversation = mongo.db.conversations.find_one({
        'user_id': user_id,
        'question_id': question_id
    })
    if conversation:
        return jsonify(conversation['history'])
    else:
        return jsonify({'message': 'No conversation found'}), 404

# @api_bp.route('/feedback/<question_id>', methods=['GET'])
# @jwt_required()
# def api_feedback(question_id):
#     try:
#         question_id = f'programming_q{question_id}'
#         user_id = get_jwt_identity()  # Get the user ID from the JWT
#         user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
#         group = user_data.get('research_group', 'experiment')
#         print(user_id)
#         # Count AI interactions for this user and question
#         personal_usage_count = mongo.db.ai_interactions.count_documents({
#             'user_id': user_id,
#             'question_id': question_id
#         })
#         
#         # Determine usage percentage
#         usage_percentage = 0 if personal_usage_count == 0 else random.randint(40, 90)
#         
#         # Get the most recent activity record for this question
#         activity_record = mongo.db.user_activities.find_one({
#             'user_id': user_id,
#             'activity': question_id,
#             'end_time': {'$ne': None}
#         }, sort=[('end_time', -1)])
#         
#         if activity_record and activity_record.get('start_time') and activity_record.get('end_time'):
#             start_time = activity_record['start_time']
#             end_time = activity_record['end_time']
#         else:
#             # Fallback: check submission timestamp
#             submission = mongo.db.submissions.find_one({
#                 'user_id': user_id,
#                 'question_id': question_id
#             })
#             
#             if submission and submission.get('timestamp'):
#                 end_time = submission['timestamp']
#                 duration = 20 if question_id == 'programming_q1' else 30
#                 start_time = end_time - datetime.timedelta(minutes=duration)
#             else:
#                 # Final fallback: use AI interactions or default times
#                 interactions = list(mongo.db.ai_interactions.find({
#                     'user_id': user_id,
#                     'question_id': question_id
#                 }).sort('timestamp', 1))
#                 
#                 if interactions:
#                     start_time = interactions[0]['timestamp']
#                     end_time = interactions[-1]['timestamp']
#                     if (end_time - start_time).total_seconds() < 600:
#                         end_time = start_time + datetime.timedelta(minutes=10)
#                 else:
#                     end_time = datetime.datetime.utcnow()
#                     start_time = end_time - datetime.timedelta(minutes=20)
#         
#         # Ensure a minimum session duration
#         min_duration = 20 if question_id == 'programming_q1' else 30
#         total_duration = max(min_duration, (end_time - start_time).total_seconds() / 60)
#         total_duration_rounded = math.ceil(total_duration / 2) * 2  # Rounded up to nearest 2 minutes
#         
#         # Create 2-minute intervals and count interactions for each
#         time_intervals = []
#         interval_counts = []
#         for minute in range(2, int(total_duration_rounded) + 1, 2):
#             time_intervals.append(str(minute))
#             interval_start = start_time + datetime.timedelta(minutes=minute-2)
#             interval_end = start_time + datetime.timedelta(minutes=minute)
#             count = mongo.db.ai_interactions.count_documents({
#                 'user_id': user_id,
#                 'question_id': question_id,
#                 'timestamp': {
#                     '$gte': interval_start,
#                     '$lt': interval_end
#                 }
#             })
#             interval_counts.append(count)
#         
#         time_data = {
#             'labels': time_intervals,
#             'values': interval_counts
#         }
#         
#         # Determine next step based on question_id
#         page_num = question_id.replace('programming_q', '')
#         if page_num == '1':
#             next_page_num = '2'
#             next_url = url_for('programming_question', page_num=next_page_num)
#         else:
#             next_page_num = 'survey'
#             next_url = url_for('api_postsurvey')
#         
#         # Prepare feedback data
#         feedback_data = {
#             'user_id': user_id,
#             'question_id': question_id,
#             'timestamp': datetime.datetime.now(datetime.UTC),
#             'personal_usage_count': personal_usage_count,
#             'usage_percentage': usage_percentage,
#             'time_data': time_data,
#             'session_start': start_time,
#             'session_end': end_time,
#             'session_duration_minutes': total_duration
#         }
#         
#         if group == 'control':
#             feedback_data['personal_usage_count'] = 0
#             feedback_data['usage_percentage'] = 0
#         
#         # Save feedback data with upsert
#         mongo.db.feedback.update_one(
#             {'user_id': user_id, 'question_id': question_id},
#             {'$set': feedback_data},
#             upsert=True
#         )
#         
#         # Return feedback information as JSON
#         return jsonify({
#             'status': 'success',
#             'feedback': feedback_data,
#             'next': {
#                 'page_num': next_page_num,
#                 'url': next_url
#             }
#         })
#     
#     except Exception as e:
#         print(f"Error in feedback route: {str(e)}")
#         traceback.print_exc()
#         return jsonify({'status': 'error', 'message': 'Error loading feedback data'}), 500

# ------------------------------
# API Route for Post-Survey
# ------------------------------
@api_bp.route('/postSurvey', methods=['GET', 'POST'])
@jwt_required()
def api_postsurvey():
    user_id = get_jwt_identity()
    
    if request.method == 'GET':
        track_activity_start(user_id, 'postsurvey')
        questions = list(mongo.db.postSurveyQuestion.find({}))
        for question in questions:
            # If using PyMongo, question['_id'] is usually an ObjectId so str() converts it properly.
            question['id'] = str(question['_id'])
            del question['_id']
        return jsonify({'questions': questions})
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'status': 'error', 'message': 'No data provided'}), 400
            
            # Retrieve questions to validate answers
            questions = list(mongo.db.postSurveyQuestion.find())
            answers = {}
            
            for question in questions:
                key = f"question_{question['_id']}"
                answer = data.get(key)
                if answer:
                    answers[key] = answer
            
            if len(answers) != len(questions):
                return jsonify({'status': 'error', 'message': 'Please answer all questions', 'answers_received': answers}), 400
            
            submission = {
                'user_id': user_id,
                'answers': answers,
                'submitted_at': datetime.datetime.now(datetime.UTC)
            }
            
            mongo.db.postSurveyAnswers.insert_one(submission)
            track_activity_end(user_id, 'postsurvey')
            
            # Update user status as complete
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {'completed': True, 'completion_date': datetime.datetime.now(datetime.UTC)}}
            )
            
            return jsonify({'status': 'success', 'message': 'Survey submitted successfully'})
        
        except Exception as e:
            print("Error in postSurvey:", str(e))
            traceback.print_exc()
            return jsonify({'status': 'error', 'message': 'An error occurred while submitting the survey'}), 500

# ------------------------------
# API Route for Completion Page
# ------------------------------
@api_bp.route('/completion', methods=['GET'])
@jwt_required()
def api_completion():
    try:
        user_id = get_jwt_identity()
        # Retrieve additional user info if necessary (e.g. name)
        user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        user_name = user.get('name') if user else 'User'
        now = datetime.datetime.now()
        
        return jsonify({
            'status': 'success',
            'completion': {
                'user_name': user_name,
                'timestamp': now.isoformat()
            }
        })
    
    except Exception as e:
        print("Error in completion route:", str(e))
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': 'Could not load completion data'}), 500



@api_bp.route('/run_code_raw', methods=['POST'])
@jwt_required()
def run_code_raw():
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()  # Expecting JSON body with key 'code'
        code = data.get('code')
        if not code.strip():
            return jsonify({'status': 'error', 'message': 'Code is empty'}), 400

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name

        # Run the code using subprocess
        process = subprocess.Popen(
            ['python3', temp_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(timeout=10)

        # Clean up the temp file
        os.unlink(temp_file)

        return jsonify({
            'status': 'success',
            'stdout': stdout.strip(),
            'stderr': stderr.strip()
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            'status': 'error',
            'stderr': 'Execution timed out (10 seconds)'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'stderr': str(e)
        }), 500


def run_code_simple(code):
    try:
        old_stdout = sys.stdout
        redirected_output = sys.stdout = io.StringIO()
        exec(code, {})  
        output = redirected_output.getvalue()
    except Exception:
        output = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
    return output


app.register_blueprint(api_bp, url_prefix='/api')

if __name__ == '__main__':
   app.run(debug=True)