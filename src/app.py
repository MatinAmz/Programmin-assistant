from flask import Flask, render_template, request, redirect, url_for, flash,jsonify
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
from flask_wtf.csrf import CSRFProtect



csrf = CSRFProtect()
app = Flask(__name__)
csrf = CSRFProtect(app)

app.config['MONGO_DBNAME'] = 'webapp'
app.config['SECRET_KEY'] = '***REDACTED-FLASK-SECRET-KEY***'
app.config['MONGO_URI'] = 'mongodb+srv://matinamoozadeh2020:J2BNxqWm8aDyF8QV@webapp.avtjo.mongodb.net/webapp?retryWrites=true&w=majority'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'matin.amoozadeh2020@gmail.com' 
app.config['MAIL_PASSWORD'] = '***REDACTED-GMAIL-APP-PASSWORD***' 
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True


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
            # Debug prints
            print("Form data:", request.form)
            print("Current user:", current_user.id, current_user.name)
            
            user_id = current_user.id
            user_name = current_user.name
            
            # Fetch questions and print them
            questions = list(mongo.db.preSurveyQuestion.find())
            print("Questions from DB:", questions)
            
            # Initialize answers dictionary
            answers = {}
            
            # Check each question
            for question in questions:
                key = f"question_{question['_id']}"
                answer = request.form.get(key)
                print(f"Processing {key}: {answer}")  # Debug print
                
                # Only add non-empty answers
                if answer:
                    answers[key] = answer
            
            # Check if all questions are answered
            if len(answers) != len(questions):
                print("Not all questions answered")
                flash("Please answer all questions.", "error")
                return render_template('surveys/preSurvey.html', 
                                    questions=questions, 
                                    answers=answers)
            
            # Create submission document
            submission = {
                'user_id': user_id,
                'user_name': user_name,
                'answers': answers,
                'submitted_at': datetime.datetime.utcnow()
            }
            
            # Save to database
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
        # Add a main block to handle input
        full_code = code + "\n\nif __name__ == '__main__':\n    try:\n        a = int(input())\n        b = int(input())\n        result = solution(a, b)\n        print(result)\n    except Exception as e:\n        print(f'Error: {str(e)}')"
        f.write(full_code)
        temp_file = f.name
    
    try:
        for test_case in test_cases:
            input_data = test_case.get('input', '')
            expected_output = str(test_case.get('expected_output', '')).strip()
            
            # Run the code with test input
            process = subprocess.Popen(
                ['python3', temp_file],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5  # 5 second timeout for safety
            )
            
            try:
                output, error = process.communicate(input=input_data, timeout=5)
                actual_output = output.strip()
                
                # Prepare test result
                result = {
                    'input': input_data,
                    'expected': expected_output,
                    'actual': actual_output,
                    'error': error,
                }
                
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
            'error': f'Execution error: {str(e)}',
        })
    
    finally:
        # Clean up
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
    # Get the question from MongoDB
    question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
    
    if not question:
        return redirect(url_for('error_page'))
    
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
        code = submitted.get('code') if submitted else None
    else:
        code = autosaved.get('code')
    
    return render_template('programming/programming.html', 
                         question=question,
                         code=code,
                         page_num=page_num)



# Updated route with fixed code execution
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
        f.write(code)
        temp_file = f.name
    
    try:
        for test_case in test_cases:
            # Prepare the test input
            input_data = test_case.get('input', '')
            expected_output = test_case.get('expected_output', '').strip()
            
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
                        'error': error
                    })
                else:
                    actual_output = output.strip()
                    if actual_output == expected_output:
                        test_results.append({
                            'status': 'passed',
                            'output': actual_output
                        })
                    else:
                        test_results.append({
                            'status': 'failed',
                            'output': actual_output,
                            'expected': expected_output
                        })
            except subprocess.TimeoutExpired:
                process.kill()
                test_results.append({
                    'status': 'error',
                    'error': 'Code execution timed out'
                })
    
    except Exception as e:
        test_results.append({
            'status': 'error',
            'error': str(e)
        })
    
    finally:
        # Clean up the temporary file
        try:
            os.unlink(temp_file)
        except:
            pass
    
    return render_template('programming/programming.html', 
                         question=question,
                         code=code,
                         test_results=test_results,
                         page_num=page_num)



# Load environment variables
load_dotenv()

# Initialize OpenAI client
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





@app.route('/feedback')
@login_required
def feedback():
    return render_template('feedback/feedback.html')


@app.route('/postsurvey')
@login_required
def postsurvey():
   return render_template('survey/post_survey.html')

if __name__ == '__main__':
   app.run(debug=True)