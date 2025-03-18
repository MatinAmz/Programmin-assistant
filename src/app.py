from flask import Flask,Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_pymongo import PyMongo
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required
from itsdangerous import SignatureExpired
from form import LoginForm, RegistrationForm, ForgotPasswordForm
from bson.objectid import ObjectId
from flask_mail import Mail, Message
import random
import string
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
import bcrypt
from functools import wraps
import subprocess
import tempfile
import os
import traceback
import sys
from bson import ObjectId
import datetime
from openai import OpenAI
import os
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect, generate_csrf,validate_csrf
from flask_cors import CORS



app = Flask(__name__)

CORS(app,supports_credentials=True, resources={r"/api/*": {"origins": "http://localhost:8080"}})  # Allow Vue.js frontend (assuming it's running on localhost:8080)


app.config['MONGO_DBNAME'] = 'webapp'
app.config['SECRET_KEY'] = '***REDACTED-FLASK-SECRET-KEY***'
app.config['MONGO_URI'] = 'mongodb+srv://matinamoozadeh2020:J2BNxqWm8aDyF8QV@webapp.avtjo.mongodb.net/webapp?retryWrites=true&w=majority'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'matin.amoozadeh2020@gmail.com' 
app.config['MAIL_PASSWORD'] = '***REDACTED-GMAIL-APP-PASSWORD***' 
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

csrf = CSRFProtect(app) 

api_bp = Blueprint('api', __name__)
csrf.exempt(api_bp)

mail = Mail(app)
# Setup for token generation for password reset
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

mongo = PyMongo(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# Create users collection
with app.app_context():
   if 'users' not in mongo.db.list_collection_names():
       mongo.db.create_collection('users')

class User(UserMixin):
   def __init__(self, user_data):
       self.id = str(user_data['_id'])
       self.name = user_data['name']
       self.email = user_data['email']


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
        mongo.db.users.insert_one(user)
        flash('Registration successful!')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html', title='Register', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
   form = LoginForm()
   if form.validate_on_submit():
       user = mongo.db.users.find_one({'email': form.email.data})

       if user and bcrypt.checkpw(form.password.data.encode('utf-8'), user['password'].encode('utf-8')):
           user_obj = User(user)
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
            
            flash("Survey submitted successfully!")
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
    
    # Create a temporary file for the code
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        # Add a main block to handle input based on the existing test cases
        full_code = code + "\n\nif __name__ == '__main__':\n    try:\n        a = int(input())\n        b = int(input())\n        result = solution(a, b)\n        print(result)\n    except Exception as e:\n        print(f'Error: {str(e)}')"
        f.write(full_code)
        temp_file = f.name
    
    try:
        for test_case in test_cases:
            input_data = test_case.get('input', '')
            expected_output = str(test_case.get('expected_output', '')).strip()
            
            process = subprocess.Popen(
                ['python3', temp_file],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            
            try:
                output, error = process.communicate(input=input_data, timeout=5)
                actual_output = output.strip()
                
                result = {
                    'input': input_data,
                    'expected': expected_output,
                    'actual': actual_output,
                    'error': error if error else None
                }
                
                # Only include error field if there is an error
                if not result['error']:
                    del result['error']
                
                if error:
                    result['status'] = 'error'
                elif actual_output == expected_output:
                    result['status'] = 'passed'
                else:
                    result['status'] = 'failed'
                
                results.append(result)
                
            except subprocess.TimeoutExpired:
                process.kill()
                results.append({
                    'status': 'error',
                    'error': 'Code execution timed out',
                    'input': input_data
                })
                
    except Exception as e:
        results.append({
            'status': 'error',
            'error': f'Execution error: {str(e)}'
        })
    
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    return results

@app.route('/programming/<page_num>/autosave', methods=['POST'])
@login_required
def autosave_code(page_num):
    try:
        code = request.json.get('code')
        
        # Save to autosaves collection
        mongo.db.code_autosaves.update_one(
            {
                'user_id': current_user.id,
                'question_id': f'programming_q{page_num}'
            },
            {
                '$set': {
                    'code': code,
                    'last_saved': datetime.datetime.utcnow()
                }
            },
            upsert=True
        )
        
        return jsonify({'status': 'success', 'message': 'Code auto-saved'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    

@app.route('/programming/<page_num>')
@login_required
def programming_question(page_num):
    try:
        # Get the question from MongoDB using question_id format
        question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
        print(f"Found question: {question}")  # Debug print
        
        if not question:
            print(f"No question found for programming_q{page_num}")
            flash('Programming question not found.', 'error')
            return render_template('programming/programming.html',
                            question={'question_text': 'Question not found'},
                            code='',
                            page_num=page_num)
        
        # First try to get autosaved code
        autosaved = mongo.db.code_autosaves.find_one({
            'user_id': current_user.id,
            'question_id': f'programming_q{page_num}'
        })
        
        # If no autosave exists, try to get submitted code
        if not autosaved:
            submitted = mongo.db.submissions.find_one({
                'user_id': current_user.id,
                'question_id': f'programming_q{page_num}'
            })
            code = submitted.get('code') if submitted else ''
        else:
            code = autosaved.get('code')
        
        # Add test cases if they don't exist
        if 'test_cases' not in question:
            question['test_cases'] = [
                {'input': 'babad', 'expected_output': 'bab'},
                {'input': 'cbbd', 'expected_output': 'bb'},
                {'input': 'a', 'expected_output': 'a'},
                {'input': 'ac', 'expected_output': 'a'}
            ]
        
        return render_template('programming/programming.html',
                          question=question,
                          code=code,
                          page_num=page_num)
                          
    except Exception as e:
        print(f"Error in programming_question: {str(e)}")
        traceback.print_exc()
        flash('Error loading programming question', 'error')
        return render_template('programming/programming.html',
                          question={'question_text': 'Error loading question'},
                          code='',
                          page_num=page_num)


# Load environment variables
load_dotenv()

# Initialize OpenAI client
# client = OpenAI(api_key="")
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

@app.route('/programming/<page_num>/prompt', methods=['POST'])
@login_required
def programming_prompt(page_num):
    prompt = request.form.get('prompt')
    code = request.form.get('code', '')
    question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
    
    try:
        # Send prompt directly to ChatGPT
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        # Log the interaction (optional)
        mongo.db.ai_interactions.insert_one({
            'user_id': current_user.id,
            'question_id': f'programming_q{page_num}',
            'prompt': prompt,
            'ai_response': ai_response,
            'timestamp': datetime.datetime.utcnow()
        })
        
    except Exception as e:
        ai_response = f"Error: {str(e)}"
    
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
    test_results = []
    
    # Create a temporary file to run the code
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        # Determine the right wrapper code based on question type
        if page_num == '1':  # Addition question
            full_code = code + """
if __name__ == '__main__':
    try:
        a = int(input())
        b = int(input())
        result = solution(a, b)
        print(result)
    except Exception as e:
        print(f'Error: {str(e)}')
"""
        else:  # Palindrome question
            full_code = code + """
if __name__ == '__main__':
    try:
        s = input().strip()
        result = solution(s)
        print(result)
    except Exception as e:
        print(f'Error: {str(e)}')
"""
        f.write(full_code)
        temp_file = f.name
    
    try:
        for test_case in test_cases:
            # Prepare the test input
            input_data = test_case.get('input', '')
            expected_output = str(test_case.get('expected_output', '')).strip()
            
            # Run the code with the test input
            process = subprocess.Popen(
                ['python3', temp_file],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            try:
                output, error = process.communicate(input=input_data, timeout=5)
                
                if error:
                    test_results.append({
                        'status': 'error',
                        'input': input_data,
                        'error': error
                    })
                else:
                    actual_output = output.strip()
                    test_results.append({
                        'input': input_data,
                        'expected': expected_output,
                        'actual': actual_output,
                        'status': 'passed' if actual_output == expected_output else 'failed'
                    })
            
            except subprocess.TimeoutExpired:
                process.kill()
                test_results.append({
                    'status': 'error',
                    'error': 'Code execution timed out',
                    'input': input_data
                })
    
    except Exception as e:
        test_results.append({
            'status': 'error', 
            'error': str(e)
        })
    
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    # Save submission
    mongo.db.submissions.insert_one({
        'user_id': current_user.id,
        'question_id': f'programming_q{page_num}',
        'code': code,
        'test_results': test_results,
        'submitted_at': datetime.datetime.utcnow()
    })
    
    # Return to the same page with test results instead of redirect
    # This way the user can see their test results
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
        
        flash(f'Solution submitted successfully! Score: {score:.1f}%', 'success')
        
        # For question 2, redirect directly to post-survey
        if page_num == '2':
            return redirect(url_for('postsurvey'))
        # For question 1, show feedback
        else:
            return redirect(url_for('feedback', question_id=f'programming_q{page_num}'))
        
    except Exception as e:
        print("Error in submit:", str(e))
        traceback.print_exc()
        flash('Error submitting solution', 'error')
        
        # For question 2, redirect directly to post-survey even on error
        if page_num == '2':
            return redirect(url_for('postsurvey'))
        else:
            return redirect(url_for('feedback', question_id=f'programming_q{page_num}'))

@app.route('/feedback/<question_id>')
@login_required
def feedback(question_id):
    try:
        # Get real personal usage count
        personal_usage_count = mongo.db.ai_interactions.count_documents({
            'user_id': current_user.id,
            'question_id': question_id
        })
        
        # If user never used AI, set usage percentage to 0
        # Otherwise, generate a random percentage for comparison
        import random
        if personal_usage_count == 0:
            usage_percentage = 0
        else:
            usage_percentage = random.randint(40, 90)
        
        # Create time-based data for the 1-hour session (real data)
        # We'll use 5-minute intervals (12 intervals in an hour)
        time_intervals = ['0:00', '5:00', '10:00', '15:00', '20:00', '25:00', 
                         '30:00', '35:00', '40:00', '45:00', '50:00', '55:00']
        
        # Get real interaction data
        interactions = list(mongo.db.ai_interactions.find({
            'user_id': current_user.id,
            'question_id': question_id
        }).sort('timestamp', 1))
        
        # Initialize counts for each interval
        interval_counts = [0] * len(time_intervals)
        
        # Process interactions into intervals
        if interactions:
            try:
                submission = mongo.db.submissions.find_one({
                    'user_id': current_user.id,
                    'question_id': question_id
                })
                
                if submission:
                    end_time = submission['timestamp']
                    start_time = end_time - datetime.timedelta(hours=1)
                else:
                    start_time = interactions[0]['timestamp']
                    end_time = start_time + datetime.timedelta(hours=1)
                
                for interaction in interactions:
                    timestamp = interaction['timestamp']
                    if timestamp < start_time or timestamp > end_time:
                        continue
                        
                    minutes_from_start = (timestamp - start_time).total_seconds() / 60
                    interval_index = min(int(minutes_from_start / 5), 11)
                    interval_counts[interval_index] += 1
                    
            except Exception as e:
                print(f"Error processing interaction times: {e}")
        
        # Prepare time data for template
        time_data = {
            'labels': time_intervals,
            'values': interval_counts
        }
        
        # Set the next page to programming question 2
        # Since we're only showing feedback for question 1
        next_url = url_for('programming_question', page_num=2)
        next_page_num = '2'
        
        # Save feedback data to MongoDB for this user
        feedback_data = {
            'user_id': current_user.id,
            'question_id': question_id,
            'timestamp': datetime.datetime.now(datetime.UTC),
            'personal_usage_count': personal_usage_count,
            'usage_percentage': usage_percentage,
            'time_data': time_data
        }
        
        # Save to MongoDB using upsert
        mongo.db.feedback.update_one(
            {
                'user_id': current_user.id,
                'question_id': question_id
            },
            {'$set': feedback_data},
            upsert=True
        )

        # Include next_url in the template context so it can be used in buttons
        return render_template('feedback/feedback.html',
            question_id=question_id,
            personal_usage_count=personal_usage_count,
            usage_percentage=usage_percentage,
            time_data=time_data,
            next_page_num=next_page_num,
            next_url=next_url
        )

    except Exception as e:
        print(f"Error in feedback route: {str(e)}")
        flash('Error loading feedback data', 'error')
        return render_template('feedback/feedback.html', question_id=question_id)

@app.route('/postSurvey', methods=['GET', 'POST'])
@login_required
def postsurvey():
    if request.method == 'GET':
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
            
            print("Saving submission:", submission)
            mongo.db.postSurveyAnswers.insert_one(submission)
            
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




@api_bp.route('/get-csrf-token', methods=['GET'])
def get_csrf():
    csrf_token = generate_csrf()  # Generate the CSRF token
    response = make_response(jsonify({"csrf_token": csrf_token}))
    response.set_cookie('csrf_token', csrf_token, httponly=False, samesite='Lax')
    return response

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

    return jsonify({
        'status': 'success',
        'message': 'Registration successful!',
        'user': {
            'id': str(new_user['_id']),
            'name': new_user['name'],
            'email': new_user['email']
        }
    }), 201

@api_bp.route('/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No input data provided'}), 400
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({'status': 'error', 'message': 'Missing email or password'}), 400

    user = mongo.db.users.find_one({'email': email})
    if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        user_obj = User(user)
        login_user(user_obj)
        return jsonify({
            'status': 'success',
            'message': 'Login successful!',
            'user': {
                'id': user_obj.id,
                'name': user_obj.name,
                'email': user['email']
            }
        })
    else:
        return jsonify({'status': 'error', 'message': 'Invalid email or password'}), 401

app.register_blueprint(api_bp, url_prefix='/api')

if __name__ == '__main__':
   app.run(debug=True)
