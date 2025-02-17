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
                'submitted_at': datetime.datetime.now(datetime.UTC)  # Fixed datetime
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
        test_results.append({'status': 'error', 'error': str(e)})
    
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
    
    # Redirect to feedback page after submission
    return redirect(url_for('programming_question', page_num=page_num))

@app.route('/programming/<page_num>/submit', methods=['POST'])
@login_required
def programming_submit(page_num):
    print(f"Received submission for page {page_num}")  # Add this line right here, at the start
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
        
        # If this was the first question and they passed, go to the next question
        if page_num == '1' and score >= 80:
            next_question = mongo.db.programmingQuestions.find_one({'question_id': 'programming_q2'})
            if next_question:
                return redirect(url_for('feedback', question_id=f'programming_q{page_num}'))

        
        return redirect(url_for('feedback', question_id=f'programming_q{page_num}'))

        
    except Exception as e:
        print("Error in submit:", str(e))
        traceback.print_exc()
        flash('Error submitting solution', 'error')
        return redirect(url_for('feedback', question_id=f'programming_q{page_num}'))

@app.route('/feedback/<question_id>')
@login_required
def feedback(question_id):
    try:
        # Get personal usage count
        personal_usage_count = mongo.db.ai_interactions.count_documents({
            'user_id': current_user.id,
            'question_id': f'programming_q{question_id}'
        })

        # Get usage by hour for time series
        pipeline = [
            {
                '$match': {
                    'user_id': current_user.id,
                    'question_id': f'programming_q{question_id}'
                }
            },
            {
                '$group': {
                    '_id': {
                        '$hour': '$timestamp'
                    },
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'_id': 1}}
        ]
        
        hourly_usage = list(mongo.db.ai_interactions.aggregate(pipeline))
        
        # Prepare data for template
        time_data = {
            'labels': [f'{h:02d}:00' for h in range(24)],
            'values': [0] * 24
        }
        
        for item in hourly_usage:
            time_data['values'][item['_id']] = item['count']

        # Get recent interactions
        recent_interactions = list(mongo.db.ai_interactions.find({
            'user_id': current_user.id,
            'question_id': f'programming_q{question_id}'
        }).sort('timestamp', -1).limit(5))

        # Get the class average usage
        class_usage_pipeline = [
            {
                '$match': {
                    'question_id': f'programming_q{question_id}'
                }
            },
            {
                '$group': {
                    '_id': '$user_id',
                    'total_count': {'$sum': 1}
                }
            }
        ]
        class_usage = list(mongo.db.ai_interactions.aggregate(class_usage_pipeline))
        total_class_interactions = sum([entry['total_count'] for entry in class_usage])
        average_usage = total_class_interactions / len(class_usage) if len(class_usage) > 0 else 0

        # Get most active hour (class level)
        most_active_hour = max(hourly_usage, key=lambda x: x['count'])['_id'] if hourly_usage else 0

        # Prepare comparison data for chart
        comparison_data = {
            'labels': ['Your Usage', 'Class Average'],
            'values': [personal_usage_count, average_usage]
        }

        return render_template('feedback/feedback.html',
            question_id=question_id,
            personal_usage_count=personal_usage_count,
            time_data=time_data,
            recent_interactions=recent_interactions,
            comparison_data=comparison_data,
            average_usage=average_usage,
            most_active_hour=most_active_hour
        )

    except Exception as e:
        print(f"Error in feedback route: {str(e)}")
        flash('Error loading feedback data', 'error')
        return render_template('feedback/feedback.html', question_id=question_id)

@app.route('/postSurvey')
@login_required
def postsurvey():
   return render_template('survey/post_survey.html')

if __name__ == '__main__':
   app.run(debug=True)