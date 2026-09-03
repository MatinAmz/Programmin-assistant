from flask import Flask, Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
import random
from flask_pymongo import PyMongo
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
from form import LoginForm, RegistrationForm, ForgotPasswordForm
from bson.objectid import ObjectId
from flask_mail import Mail, Message
import string
import bcrypt
import subprocess
import tempfile
import os
import traceback
import sys
import datetime
import pytz
from openai import OpenAI
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
import io
import shutil
import platform
import threading
import json
import re

try:
    import resource
except Exception:
    resource = None

try:
    from dns import resolver 
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False
    print("Warning: dnspython not installed. Email domain validation will be limited.")

EXEC_SEMAPHORE = threading.BoundedSemaphore(value=2)


# Load environment variables from src/.env before anything reads them.
load_dotenv()

app = Flask(__name__)

# Comma-separated list of allowed frontend origins, e.g.
# "http://localhost:8080,https://your-frontend.onrender.com"
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get('ALLOWED_ORIGINS', 'http://localhost:8080').split(',') if o.strip()
]

CORS(app, resources={
    r"/api/*": {
        "origins": ALLOWED_ORIGINS,
        "supports_credentials": True
    }
})

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
mail = Mail(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
mongo = PyMongo(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# ============= Helper Functions =============
def _limit_child_resources():
    """Limit resources for child processes"""
    if resource is None:
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
        mem = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except Exception:
        pass

# ============= Initialize Collections =============
def initialize_conversations_collection():
    with app.app_context():
        if 'conversations' not in mongo.db.list_collection_names():
            mongo.db.create_collection('conversations')
            mongo.db.conversations.create_index([('user_id', 1), ('question_id', 1)], unique=True)

def initialize_srl_collections():
    """Initialize SRL-related MongoDB collections"""
    with app.app_context():
        if 'srl_conversation_states' not in mongo.db.list_collection_names():
            mongo.db.create_collection('srl_conversation_states')
            mongo.db.srl_conversation_states.create_index([('user_id', 1), ('question_id', 1)], unique=True)
        if 'user_feedback' not in mongo.db.list_collection_names():
            mongo.db.create_collection('user_feedback')
            mongo.db.user_feedback.create_index([('user_id', 1), ('question_id', 1), ('timestamp', -1)])

initialize_conversations_collection()
initialize_srl_collections()
# ========== SRL PROMPT CONSTANTS ==========

SRL_SYSTEM_CORE = """
You are an SRL (Self-Regulated Learning) coding coach for C++ students.
Your job is to guide through Planning → Monitoring → Reflection without giving solutions.
NEVER write solution code for users.
Keep replies ≤ 200 words unless the user explicitly asks for more.
End every reply with 1–2 short questions prompting next action.

ABSOLUTE RULES
- Do NOT output any code in any language (no fenced blocks, no snippets, no signatures).
- Use non-code analogies from other domains (bookstore, library, restaurant) to illustrate concepts; never use assignment-specific names (do not use BankAccount or similar).
- If the user asks for “syntax”, provide a boilerplate pattern with placeholders.
- Explain patterns conceptually: "Think of it like organizing a filing cabinet..."
- Prefer questions over answers; keep replies ~200 words unless asked for more.
- End every reply with 1–2 short questions that prompt the next action.

MESSAGE SHAPE
1) A bold phase header (one of: **Planning**, **Monitoring**, **Reflection**)
2) 3–5 bullets tailored to THIS problem using conceptual guidance
3) 1–2 short questions prompting the next action
"""


PLANNING_HINT = """
**Planning**
- Break THIS problem into 3–4 concrete steps tied to its exact requirements.
- Identify what data (state) and what actions (methods) are needed.
- Offer a boilerplate pattern ONLY if the student asks about syntax; avoid any compilable code.
- Do NOT provide any assignment code.
End with: Which step would you like to start with, and what will you try first?
"""

MONITORING_HINT = """
**Monitoring**
- Compare expected vs. actual behavior; ask where state changes.
- Suggest 1–2 micro-experiments (describe what to observe, not code to paste).
- Keep any syntax help as a plain-text pattern, never full assignment logic.

End with: What did you observe after the micro-experiment, and where did the behavior diverge from expectations?
"""
REFLECTION_HINT = """
**Reflection**
- Celebrate briefly, then propose one small improvement (naming, guard conditions, repetition removal, complexity).
- Keep suggestions incremental and safe; no big redesigns unless asked.
- Do not rewrite their code; describe the improvement and why.

End with: What part was most challenging, and what strategy would you reuse next time?
"""


REAL_WORLD_ANALOGIES = {
    "class_structure": """
Think of a class like a **BLUEPRINT FOR A HOUSE**:
- Private members = rooms you can't see from outside (bedroom, bathroom)
- Public methods = doors and windows that let people interact with the house
- Constructor = the building process that sets up the house initially
The blueprint defines what every house of this type will have, but each actual house (object) has its own specific values.
""",
    
    "encapsulation": """
Think of encapsulation like a **VENDING MACHINE**:
- You can't reach inside and grab items directly (private data)
- You use buttons to interact with it (public methods)
- The machine controls what you can do (enforces rules)
This protects the internal state and ensures everything happens correctly.
""",
    
    "constructor": """
Think of a constructor like **SETTING UP A NEW PHONE**:
- When you first get it, you enter your name, language, time zone
- These initial settings make the phone ready to use
- Without setup, the phone wouldn't work properly
A constructor does the same thing - it sets up initial values so the object is ready to use.
""",
    
    "guard_conditions": """
Think of guard conditions like a **BOUNCER AT A CLUB**:
- The bouncer checks: Are you old enough? Do you have ID?
- If requirements aren't met, you don't get in
- This prevents problems before they happen
Your code does the same - it checks "Is this input valid?" before proceeding.
""",
    
    "state_management": """
Think of managing state like **KEEPING TRACK OF YOUR BANK ACCOUNT**:
- You need to know your current balance (state)
- Every deposit or withdrawal changes that balance
- You can't withdraw more than you have (rule enforcement)
Your code tracks values and updates them based on what happens.
""",
    
    "method_design": """
Think of methods like **APPLIANCE BUTTONS**:
- A microwave has buttons: Start, Stop, Add Time
- Each button does ONE specific thing
- You don't need to know HOW the microwave works internally
Methods are the same - each does one clear job, and users don't need to know the implementation details.
""",
    
    "testing": """
Think of testing like **TASTE-TESTING A RECIPE**:
- You try a small sample to see if it's right
- If it's too salty, you adjust before serving the whole meal
- You check different aspects: taste, texture, temperature
Testing code is similar - try small pieces, check the results, fix problems early.
"""
}

REFUSAL_TEMPLATE = """
REFUSAL & REDIRECT
If asked for the complete solution: 
"I can't provide the full solution—my role is to coach your process. Think of it this way: if I gave you the answer, you wouldn't build the problem-solving skills you need for the next challenge. Let me guide you through the thinking process instead. Which part are you stuck on?"

If asked for code examples:
"I can’t share code, but here’s the concept: {ANALOGY}. How would YOU translate that idea into your own code for this task? What’s your first step?"

If they're completely stuck:
"Let's break this down into smaller pieces. Imagine you're explaining to a friend how {REAL_WORLD_ANALOGY}. What would be the first step? That's exactly what your code needs to do."
"""



# ========== MAIN PROMPT BUILDER(system message) ==========

def build_natural_srl_prompt(question_text, code, terminal_output, conversation_history, current_step_info):
    # ------ Lightweight context shaping ------
    def _brief(txt, limit):
        if not txt:
            return "None"
        txt = txt.strip()
        return (txt[:limit] + "…") if len(txt) > limit else txt
    
    code_brief = _brief(code, 1200)
    out_brief = _brief(terminal_output, 1000)
    is_first_message = len(conversation_history) == 0
    has_minimal_code = not code or len(code.strip()) < 50
    has_output = bool(terminal_output and terminal_output.strip())
    all_tests_passed = ('passed' in terminal_output.lower() and 
                       'failed' not in terminal_output.lower()) if has_output else False
    
    # ------ Syntax error detection ------
    syntax_keywords = ['syntax error', 'expected', 'undeclared', 'parse error', 
                       'missing', 'unexpected', 'invalid syntax', 'error:', 'undefined']
    has_syntax_error = any(keyword in terminal_output.lower() 
                          for keyword in syntax_keywords) if has_output else False
    
    # ------ Phase determination and analogy selection ------
    if is_first_message or has_minimal_code:
        phase = "PLANNING"
        phase_instruction = PLANNING_HINT
        suggested_analogies = [
            REAL_WORLD_ANALOGIES["class_structure"],
            REAL_WORLD_ANALOGIES["constructor"]
        ]
    elif all_tests_passed:
        phase = "REFLECTION"
        phase_instruction = REFLECTION_HINT
        suggested_analogies = [
            REAL_WORLD_ANALOGIES["encapsulation"],
            REAL_WORLD_ANALOGIES["testing"]
        ]
    else:
        phase = "DEBUGGING"
        if has_syntax_error:
            # Enhanced debugging for syntax issues
            phase_instruction = """
**Debugging → Syntax Issue Detected**
- Identify the TYPE of syntax issue (e.g., "missing piece in the structure", "incorrect order of elements") using conceptual language.
- Use an analogy: "It's like trying to assemble furniture but missing a screw - the structure isn't complete."
- Ask: "Look at the error message carefully. What piece is it expecting that's not there?"


End with: What did you change, and what happened when you compiled again?
"""
            suggested_analogies = [
                REAL_WORLD_ANALOGIES["constructor"],
                REAL_WORLD_ANALOGIES["class_structure"]
            ]
        else:
            phase_instruction = MONITORING_HINT
            suggested_analogies = [
                REAL_WORLD_ANALOGIES["guard_conditions"],
                REAL_WORLD_ANALOGIES["state_management"]
            ]
    
    # ------ Extract class names from question to prevent them in discussion ------
    forbidden_terms = []
    import re
    class_matches = re.findall(r'\b([A-Z][a-zA-Z]+)\b', question_text)
    forbidden_terms.extend(class_matches[:5])
    
    forbidden_list = ", ".join(forbidden_terms) if forbidden_terms else "assignment-specific names"
    
    # ------ Build analogies section ------
    analogies_section = ""
    if suggested_analogies:
        analogies_section = "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        analogies_section += "REAL-WORLD ANALOGIES (use if helpful for conceptual clarity):\n"
        analogies_section += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        analogies_section += "\n".join(suggested_analogies)
    
    # ------ Compose final system message ------
    return f"""
{SRL_SYSTEM_CORE}

═══════════════════════════════════════════════════════════════
TASK CONTEXT
═══════════════════════════════════════════════════════════════
Problem Statement:
{question_text}

═══════════════════════════════════════════════════════════════
STUDENT CONTEXT
═══════════════════════════════════════════════════════════════
Current Code (trimmed):
{code_brief}

Latest Output/Tests (trimmed):
{out_brief}

Step Info: {current_step_info}
Syntax Error Detected: {has_syntax_error}
Phase: {phase}

═══════════════════════════════════════════════════════════════
PHASE BEHAVIOR
═══════════════════════════════════════════════════════════════
{phase_instruction}

═══════════════════════════════════════════════════════════════
CRITICAL INSTRUCTION: CODE EXAMPLES FROM OTHER DOMAINS
═══════════════════════════════════════════════════════════════
- Do show code examples from different domains to illustrate concepts
- Guide with questions, not code snippets
- Help them understand the PATTERN, not copy a different implementation

Forbidden Assignment Terms (never discuss these directly): {forbidden_list}

{REFUSAL_TEMPLATE}
{analogies_section}

═══════════════════════════════════════════════════════════════
NOW RESPOND
═══════════════════════════════════════════════════════════════
Produce your response following MESSAGE SHAPE above.
Be warm, use analogies to explain concepts, and end with 1-2 questions that prompt action.
Keep response under 200 words unless more detail is explicitly requested.
Do NOT output any code in any language (no fenced blocks, no snippets, no signatures).
"""


if __name__ == "__main__":
    # Example usage
    question = """
    Create a BankAccount class with:
    - Private members: customerName, checkingBalance, savingsBalance
    - Constructor to initialize all values
    - Getter/setter methods for all members
    - Methods: DepositChecking, WithdrawSavings, TransferToSavings
    """
    
    code = """
    class BankAccount {
    public:
        BankAccount(string name, double checking, double savings)
    """
    
    output = "error: expected '{' after constructor declaration"
    
    prompt = build_natural_srl_prompt(
        question_text=question,
        code=code,
        terminal_output=output,
        conversation_history=[],
        current_step_info={'step_number': 1, 'total_steps': 4}
    )
    
    print(prompt)
    print("\n" + "="*70)
    print("EXPECTED AI RESPONSE STYLE:")
    print("="*70)
    print("""
**Debugging → Syntax Issue Detected**

I can see the compiler is expecting something after your constructor parameters. 

Think of it like this: When you write instructions for assembling furniture, you need:
1. The list of parts (your parameters)
2. The actual assembly steps (the constructor body)

Your code has the parts list but is missing the body where the assembly happens. The body should show HOW to use those parameters to set up your object.

What element comes after the parameter list to contain the initialization logic?
What did you change, and what happened when you compiled again?
""")



class SRLConversationManager:
    """Manages SRL conversation state for users"""
    
    @staticmethod
    def get_or_create_state(user_id, question_id):
        """Get existing SRL state or create a new one"""
        state = mongo.db.srl_conversation_states.find_one({
            'user_id': user_id,
            'question_id': question_id
        })
        
        if not state:
            # Create initial state
            state = {
                'user_id': user_id,
                'question_id': question_id,
                'phase': 'PLANNING',
                'step_number': 0,
                'total_steps': 4,
                'current_step_name': 'Getting Started',
                'interaction_count': 0,
                'confidence_ratings': [],
                'created_at': datetime.datetime.utcnow(),
                'last_updated': datetime.datetime.utcnow()
            }
            mongo.db.srl_conversation_states.insert_one(state)
        
        return state
    
    @staticmethod
    def update_state(user_id, question_id, updates):
        """Update SRL state with new information"""
        updates['last_updated'] = datetime.datetime.utcnow()
        
        mongo.db.srl_conversation_states.update_one(
            {'user_id': user_id, 'question_id': question_id},
            {'$set': updates},
            upsert=True
        )
    
    @staticmethod
    def get_phase_summary(user_id, question_id):
        """Get summary of user's SRL phases"""
        state = mongo.db.srl_conversation_states.find_one({
            'user_id': user_id,
            'question_id': question_id
        })
        
        if not state:
            return None
        
        return {
            'current_phase': state.get('phase', 'PLANNING'),
            'step_progress': f"{state.get('step_number', 0)}/{state.get('total_steps', 4)}",
            'interaction_count': state.get('interaction_count', 0),
            'average_confidence': sum(r['rating'] for r in state.get('confidence_ratings', [])) / len(state.get('confidence_ratings', [])) if state.get('confidence_ratings') else None
        }

def detect_srl_phase_from_conversation(ai_response, user_prompt, code, terminal_output, current_phase):
    """Detect which SRL phase based on conversation"""
    ai_lower = ai_response.lower()
    user_lower = user_prompt.lower() if user_prompt else ""
    
    if any(phrase in ai_lower for phrase in ['step 1:', 'step 2:', "i've broken", 'break it down']):
        return 'PLANNING'
    
    if terminal_output or len(code) > 100:
        if any(phrase in ai_lower for phrase in ['try', 'implement', 'run your code', 'check your']):
            return 'MONITORING'
    
    if any(phrase in ai_lower for phrase in ['you solved it', 'awesome work', 'completed']):
        return 'REFLECTION'
    
    return current_phase

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

def track_activity_start(user_id, activity):
    """Record when a user starts an activity"""
    mongo.db.user_activities.insert_one({
        'user_id': user_id,
        'activity': activity,
        'start_time': datetime.datetime.utcnow(),
        'end_time': None
    })


def track_activity_end(user_id, activity):
    """Record when a user finishes an activity and calculate duration"""
    current_time = datetime.datetime.utcnow()
    
    # Find the most recent activity record
    activity_record = mongo.db.user_activities.find_one(
        {'user_id': user_id, 'activity': activity, 'end_time': None},
        sort=[('start_time', -1)]
    )
    
    if activity_record:
        # Calculate duration in seconds and minutes
        duration_seconds = (current_time - activity_record['start_time']).total_seconds()
        duration_minutes = round(duration_seconds / 60, 2)
        
        # Update with end time and duration
        mongo.db.user_activities.update_one(
            {'_id': activity_record['_id']},
            {'$set': {
                'end_time': current_time,
                'duration_seconds': duration_seconds,
                'duration_minutes': duration_minutes
            }}
        )

def is_valid_email(email):
    """Validate email format and check if domain exists"""
    # Basic format check
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return False, "Invalid email format"
    
    # Check for common fake/temporary email domains
    fake_domains = [
        'test.com', 'example.com', 'fake.com', 'dummy.com', 
        'temp.com', 'temporary.com', 'throwaway.com', 'tempmail.com',
        'mailinator.com', '10minutemail.com', 'guerrillamail.com',
        'trashmail.com', 'yopmail.com', 'maildrop.cc', 'getnada.com',
        'fakeinbox.com', 'throwawaymail.com', 'spam4.me', 'tempmail.org'
    ]
    
    domain = email.split('@')[1].lower()
    if domain in fake_domains:
        return False, "Temporary email addresses are not allowed"
    
    # Verify domain has MX records (requires dnspython)
    if DNS_AVAILABLE:
        try:
            mx_records = resolver.resolve(domain, 'MX')
            if not mx_records:
                return False, "Email domain does not exist"
        except resolver.NXDOMAIN:
            return False, "Email domain does not exist"
        except resolver.NoAnswer:
            return False, "Email domain has no mail server"
        except Exception as e:
            # If we can't check, allow it (might be network issue)
            print(f"Email validation warning: {str(e)}")
            pass
    
    return True, "Valid email"

# ============= Initialize Success Tracking Collection =============
def initialize_success_tracking():
    """Initialize collection to track successful completions"""
    with app.app_context():
        if 'user_success' not in mongo.db.list_collection_names():
            mongo.db.create_collection('user_success')
            mongo.db.user_success.create_index([('user_id', 1), ('question_id', 1)], unique=True)
# Call this after other initializations
initialize_success_tracking()
# ============= Track Success Function =============
def track_user_success(user_id, question_id, passed_all_tests, score, test_results):
    """Track when a user successfully completes a question"""
    try:
        user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        
        success_record = {
            'user_id': user_id,
            'user_name': user.get('name', 'Unknown') if user else 'Unknown',
            'user_email': user.get('email', 'Unknown') if user else 'Unknown',
            'question_id': question_id,
            'passed_all_tests': passed_all_tests,
            'score': score,
            'total_tests': len(test_results),
            'passed_tests': sum(1 for r in test_results if r.get('status') == 'passed'),
            'timestamp': datetime.datetime.utcnow(),
            'submission_date': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Upsert - update if exists, insert if new
        mongo.db.user_success.update_one(
            {'user_id': user_id, 'question_id': question_id},
            {'$set': success_record},
            upsert=True
        )
        
        print(f"✅ Success tracked: User {user_id} - {question_id} - Score: {score}%")
        
    except Exception as e:
        print(f"Error tracking success: {str(e)}")

def _insert_login_log(email, user_id):
    """Helper to insert a login log for email."""
    last_log = mongo.db.login_logs.find_one(sort=[("login_sequence", -1)])
    if last_log and "login_sequence" in last_log:
        next_sequence = last_log["login_sequence"] + 1
    else:
        next_sequence = 1
    now_central = datetime.datetime.now(pytz.timezone('America/Chicago'))
    login_log = {
        "user_id": user_id,
        "email": email,
        "login_sequence": next_sequence,
        "time": now_central
    }
    mongo.db.login_logs.insert_one(login_log)

def run_cpp_multifile(files_dict: dict, input_data: str = "", timeout_sec: int = 5):
    """
    Compile and run multiple C++ files together
    
    Args:
        files_dict: {"filename.cpp": "code content", "header.h": "header content"}
        input_data: stdin input for the program
        timeout_sec: execution timeout
    
    Returns:
        dict with status, stdout, stderr
    """
    gxx = shutil.which("g++")
    if not gxx:
        return {"status": "error", "stdout": "", "stderr": "g++ not found on server"}
    
    if not EXEC_SEMAPHORE.acquire(timeout=0.5):
        return {"status": "busy", "stdout": "", "stderr": "Runner busy, please retry."}
    
    try:
        with tempfile.TemporaryDirectory() as td:
            # Write all files to temp directory
            cpp_files = []
            for filename, content in files_dict.items():
                filepath = os.path.join(td, filename)
                with open(filepath, "w") as f:
                    f.write(content)
                
                # Track .cpp files for compilation
                if filename.endswith('.cpp'):
                    cpp_files.append(filepath)
            
            # Compile all .cpp files together
            exe = os.path.join(td, "main.exe" if platform.system() == "Windows" else "main.out")
            
            compile_cmd = [gxx, "-std=c++17", "-O2"] + cpp_files + ["-o", exe]
            
            compile_proc = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                timeout=20,
                cwd=td  # Set working directory so #include works
            )
            
            if compile_proc.returncode != 0:
                return {
                    "status": "compile_error",
                    "stdout": compile_proc.stdout,
                    "stderr": compile_proc.stderr
                }
            
            # Run the compiled program
            try:
                proc = subprocess.Popen(
                    [exe],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=_limit_child_resources if (platform.system() != "Windows" and resource is not None) else None
                )
                out, err = proc.communicate(input=input_data, timeout=timeout_sec)
                return {"status": "ok", "stdout": out, "stderr": err}
            except subprocess.TimeoutExpired:
                proc.kill()
                return {"status": "timeout", "stdout": "", "stderr": "Execution timed out"}
                
    except Exception as e:
        return {"status": "error", "stdout": "", "stderr": str(e)}
    finally:
        EXEC_SEMAPHORE.release()


def run_code_with_test_cases_multifile(language: str, files_dict: dict, test_cases: list):
    """
    Run multi-file code with test cases
    
    Args:
        language: "cpp" 
        files_dict: {"BankAccount.h": "...", "BankAccount.cpp": "...", "main.cpp": "..."}
        test_cases: list of test case dicts
    """
    if not test_cases:
        return [{"test_name": "No tests", "status": "error", "error": "No test cases configured"}]
    
    if language.lower() != "cpp":
        return [{"test_name": "Runner", "status": "error", "error": "Multi-file only supports C++"}]
    
    gxx = shutil.which("g++")
    if not gxx:
        return [{"test_name": "Compile", "status": "error", "error": "g++ not found"}]
    
    results = []
    
    try:
        with tempfile.TemporaryDirectory() as td:
            # Write all files
            cpp_files = []
            for filename, content in files_dict.items():
                filepath = os.path.join(td, filename)
                with open(filepath, "w") as f:
                    f.write(content)
                if filename.endswith('.cpp'):
                    cpp_files.append(filepath)
            
            exe = os.path.join(td, "main.exe" if platform.system() == "Windows" else "main.out")
            
            # Compile
            compile_proc = subprocess.run(
                [gxx, "-std=c++17", "-O2"] + cpp_files + ["-o", exe],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=td
            )
            
            if compile_proc.returncode != 0:
                return [{
                    "test_name": "Compile",
                    "status": "compile_error",
                    "input": "",
                    "expected": "",
                    "actual": compile_proc.stdout,
                    "error": compile_proc.stderr
                }]
            
            # Run test cases
            for i, tc in enumerate(test_cases, 1):
                name = tc.get("test_name", f"Test Case {i}")
                expected = (tc.get("expected_output") or "").strip()
                input_data = tc.get("input") or ""
                
                try:
                    if not EXEC_SEMAPHORE.acquire(timeout=0.5):
                        results.append({
                            "test_name": name,
                            "status": "error",
                            "error": "Runner busy, please retry.",
                            "input": input_data
                        })
                        continue
                    
                    proc = subprocess.Popen(
                        [exe],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        preexec_fn=_limit_child_resources if (platform.system() != "Windows" and resource is not None) else None
                    )
                    
                    out, err = proc.communicate(input=input_data, timeout=5)
                    actual = (out or "").strip()
                    ok = (" ".join(actual.split()) == " ".join(expected.split()))
                    
                    results.append({
                        "test_name": name,
                        "input": input_data,
                        "expected": expected,
                        "actual": actual,
                        "status": "passed" if ok else "failed",
                        **({"stderr": err} if err else {})
                    })
                    
                except subprocess.TimeoutExpired:
                    proc.kill()
                    results.append({
                        "test_name": name,
                        "status": "error",
                        "error": "Execution timed out (5s)",
                        "input": input_data
                    })
                finally:
                    try:
                        EXEC_SEMAPHORE.release()
                    except Exception:
                        pass
                        
    except Exception as e:
        results.append({"test_name": "System", "status": "error", "error": str(e)})
    
    return results
# ============= Code Execution Functions =============
def run_code_with_test_cases(code, test_cases):
    """Run Python code with test cases"""
    results = []
    
    for i, test_case in enumerate(test_cases):
        input_data = test_case.get('input', '')
        expected_output = test_case.get('expected_output', '').strip()
        code_setup = test_case.get('code_setup', '')
        test_name = test_case.get('test_name', f'Test Case {i+1}')
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write("import sys\nimport io\nimport asyncio\n\n")
                f.write(code + "\n\n")
                
                if code_setup:
                    f.write(f"{code_setup}\n\n")
                
                f.write("""
if __name__ == '__main__':
    output_capture = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = output_capture
    
    try:
        if 'print_flow' in globals():
            print_flow()
        elif 'main' in globals():
            main()
    except Exception as e:
        print(f"Error: {str(e)}")
    
    sys.stdout = original_stdout
    print(output_capture.getvalue().strip())
""")
                temp_file = f.name
            
            process = subprocess.Popen(
                ['python3', temp_file],
                stdin=subprocess.PIPE if input_data else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            try:
                stdout, stderr = process.communicate(input=input_data if input_data else None, timeout=10)
                actual_output = stdout.strip()
                error_msg = stderr.strip()
                
                expected_norm = ' '.join(expected_output.split())
                actual_norm = ' '.join(actual_output.split())
                status = 'passed' if actual_norm == expected_norm else 'failed'
                
                if error_msg and "Traceback" in error_msg and "RuntimeWarning" not in error_msg:
                    status = 'error'
                
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
            
            if os.path.exists(temp_file):
                os.unlink(temp_file)
                
        except Exception as e:
            results.append({
                'test_name': test_name,
                'status': 'error',
                'error': f'Test runner error: {str(e)}',
                'traceback': traceback.format_exc()
            })
    
    if not results:
        results.append({
            'test_name': 'System Error',
            'status': 'error',
            'error': 'No test results were generated.',
            'actual': '',
            'expected': ''
        })
    
    return results

def run_code_with_test_cases_multi(language: str, code: str, test_cases: list):
    """Run code with test cases - supports Python and C++"""
    if not test_cases:
        return [{"test_name": "No tests", "status": "error", "error": "No test cases configured"}]
    
    if language.lower() != "cpp":
        return [{"test_name": "Runner", "status": "error", "error": f"Unsupported language: {language}"}]
    
    if language.lower() == "python":
        return run_code_with_test_cases(code, test_cases)
    
    
    
    gxx = shutil.which("g++")
    if not gxx:
        return [{"test_name": "Compile", "status": "error", "error": "g++ not found"}]
    
    results = []
    try:
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "main.cpp")
            exe = os.path.join(td, "main.exe" if platform.system() == "Windows" else "main.out")
            
            with open(src, "w") as f:
                f.write(code)
            
            compile_proc = subprocess.run(
                [gxx, "-std=c++17", "-O2", src, "-o", exe],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if compile_proc.returncode != 0:
                return [{
                    "test_name": "Compile",
                    "status": "compile_error",
                    "input": "",
                    "expected": "",
                    "actual": compile_proc.stdout,
                    "error": compile_proc.stderr
                }]
            
            for i, tc in enumerate(test_cases, 1):
                name = tc.get("test_name", f"Test Case {i}")
                expected = (tc.get("expected_output") or "").strip()
                input_data = tc.get("input") or ""
                
                try:
                    if not EXEC_SEMAPHORE.acquire(timeout=0.5):
                        results.append({
                            "test_name": name,
                            "status": "error",
                            "error": "Runner busy, please retry.",
                            "input": input_data
                        })
                        continue
                    
                    proc = subprocess.Popen(
                        [exe],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        preexec_fn=_limit_child_resources if (platform.system() != "Windows" and resource is not None) else None
                    )
                    
                    out, err = proc.communicate(input=input_data, timeout=5)
                    actual = (out or "").strip()
                    ok = (" ".join(actual.split()) == " ".join(expected.split()))
                    
                    results.append({
                        "test_name": name,
                        "input": input_data,
                        "expected": expected,
                        "actual": actual,
                        "status": "passed" if ok else "failed",
                        **({"stderr": err} if err else {})
                    })
                    
                except subprocess.TimeoutExpired:
                    proc.kill()
                    results.append({
                        "test_name": name,
                        "status": "error",
                        "error": "Execution timed out (5s)",
                        "input": input_data
                    })
                finally:
                    try:
                        EXEC_SEMAPHORE.release()
                    except Exception:
                        pass
                        
    except Exception as e:
        results.append({"test_name": "System", "status": "error", "error": str(e)})
    
    return results

def run_python_once(code: str, input_data: str = "", timeout_sec: int = 5):
    """Run Python code once with input"""
    py = shutil.which("python3") or shutil.which("python")
    if not py:
        return {"status": "error", "stdout": "", "stderr": "Python interpreter not found"}
    
    if not EXEC_SEMAPHORE.acquire(timeout=0.5):
        return {"status": "busy", "stdout": "", "stderr": "Runner busy, please retry."}
    
    try:
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "main.py")
            with open(src, "w") as f:
                f.write(code)
            
            try:
                proc = subprocess.Popen(
                    [py, src],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=_limit_child_resources if (platform.system() != "Windows" and resource is not None) else None
                )
                out, err = proc.communicate(input=input_data, timeout=timeout_sec)
                return {"status": "ok", "stdout": out, "stderr": err}
            except subprocess.TimeoutExpired:
                proc.kill()
                return {"status": "timeout", "stdout": "", "stderr": "Execution timed out"}
    except Exception as e:
        return {"status": "error", "stdout": "", "stderr": str(e)}
    finally:
        try:
            EXEC_SEMAPHORE.release()
        except Exception:
            pass

def run_cpp_once(code: str, input_data: str = "", timeout_sec: int = 5):
    """Compile and run C++ code once"""
    gxx = shutil.which("g++")
    if not gxx:
        return {"status": "error", "stdout": "", "stderr": "g++ not found on server"}
    
    if not EXEC_SEMAPHORE.acquire(timeout=0.5):
        return {"status": "busy", "stdout": "", "stderr": "Runner busy, please retry."}
    
    try:
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "main.cpp")
            exe = os.path.join(td, "main.exe" if platform.system() == "Windows" else "main.out")
            
            with open(src, "w") as f:
                f.write(code)
            
            compile_proc = subprocess.run(
                [gxx, "-std=c++17", "-O2", src, "-o", exe],
                capture_output=True,
                text=True,
                timeout=20
            )
            
            if compile_proc.returncode != 0:
                return {
                    "status": "compile_error",
                    "stdout": compile_proc.stdout,
                    "stderr": compile_proc.stderr
                }
            
            try:
                proc = subprocess.Popen(
                    [exe],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=_limit_child_resources if (platform.system() != "Windows" and resource is not None) else None
                )
                out, err = proc.communicate(input=input_data, timeout=timeout_sec)
                return {"status": "ok", "stdout": out, "stderr": err}
            except subprocess.TimeoutExpired:
                proc.kill()
                return {"status": "timeout", "stdout": "", "stderr": "Execution timed out"}
    except Exception as e:
        return {"status": "error", "stdout": "", "stderr": str(e)}
    finally:
        EXEC_SEMAPHORE.release()

# ============= User Model =============
with app.app_context():
    if 'users' not in mongo.db.list_collection_names():
        mongo.db.create_collection('users')

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.name = user_data['name']
        self.email = user_data['email']
        self.research_group = user_data.get('research_group', 'experiment')

@login_manager.user_loader
def load_user(user_id):
    user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    return User(user_data) if user_data else None

# ============= Flask Routes =============
@app.after_request
def add_no_cache_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.route('/', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data
        
        # Validate email
        is_valid, message = is_valid_email(email)
        if not is_valid:
            flash(f'Registration failed: {message}', 'error')
            return render_template('auth/register.html', title='Register', form=form)
        
        existing_user = mongo.db.users.find_one({'email': email})
        if existing_user:
            flash('Email already exists. Please login.')
            return redirect(url_for('login'))
        
        hashed_password = bcrypt.hashpw(form.password.data.encode('utf-8'), bcrypt.gensalt())
        user = {
            'name': form.name.data,
            'email': email,
            'password': hashed_password.decode('utf-8'),
            'research_group': 'experiment'
        }
        result = mongo.db.users.insert_one(user)
        
        mongo.db.user_activities.insert_one({
            'user_id': str(result.inserted_id),
            'activity': 'group_assignment',
            'group': 'experiment',
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
            # COMMENTED OUT: Random group assignment for existing users
            # if 'research_group' not in user_data or not user_data['research_group']:
            #     group = random.choice(['experiment', 'control'])
            #     mongo.db.users.update_one(
            #         {'_id': user_data['_id']},
            #         {'$set': {'research_group': group}}
            #     )
            #     mongo.db.user_activities.insert_one({
            #         'user_id': str(user_data['_id']),
            #         'activity': 'group_assignment',
            #         'group': group,
            #         'timestamp': datetime.datetime.utcnow()
            #     })
            
            # Always set to experiment if missing
            if 'research_group' not in user_data or not user_data['research_group']:
                mongo.db.users.update_one(
                    {'_id': user_data['_id']},
                    {'$set': {'research_group': 'experiment'}}
                )
            
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
            new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            mongo.db.users.update_one({'email': email}, {'$set': {'password': hashed_password.decode('utf-8')}})
            
            msg = Message("Your New Password", sender=app.config['MAIL_USERNAME'], recipients=[email])
            msg.body = f"Your new password is: {new_password}\nYou can now log in with this password."
            mail.send(msg)
            
            flash('A new password has been sent to your email.', 'info')
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
            user_id = current_user.id
            user_name = current_user.name
            questions = list(mongo.db.preSurveyQuestion.find())
            
            answers = {}
            for question in questions:
                key = f"question_{question['_id']}"
                answer = request.form.get(key)
                if answer:
                    answers[key] = answer
            
            if len(answers) != len(questions):
                flash("Please answer all questions.", "error")
                return render_template('surveys/preSurvey.html', questions=questions, answers=answers)
            
            submission = {
                'user_id': user_id,
                'user_name': user_name,
                'answers': answers,
                'submitted_at': datetime.datetime.now(datetime.timezone.utc)
            }
            
            mongo.db.preSurveyAnswers.insert_one(submission)
            track_activity_end(current_user.id, 'presurvey')
            return redirect(url_for('programming_question', page_num=1))
            
        except Exception as e:
            print("Error in preSurvey:", str(e))
            traceback.print_exc()
            flash("An error occurred. Please try again.")
            return render_template('surveys/preSurvey.html', questions=questions)

@app.route('/programming/<page_num>')
@login_required
def programming_question(page_num):
    try:
        question_id = f'programming_q{page_num}'
        track_activity_start(current_user.id, question_id)
        
        question = mongo.db.programmingQuestions.find_one({'question_id': question_id})
        if not question:
            flash('Programming question not found.', 'error')
            return render_template('programming/programming.html',
                                   question={'question_text': 'Question not found'},
                                   code='', page_num=page_num)
        
        autosaved = mongo.db.code_autosaves.find_one(
            {'user_id': current_user.id, 'question_id': question_id},
            sort=[('saved_at', -1)]
        )
        
        if not autosaved:
            submitted = mongo.db.submissions.find_one({
                'user_id': current_user.id,
                'question_id': question_id
            })
            code = submitted.get('code') if submitted and submitted.get('code') else question.get('starter_code', '')
        else:
            code = autosaved.get('code')
        
        timer_duration = 20 if page_num == '1' else 30
        
        # COMMENTED OUT: Control group logic
        # group = getattr(current_user, 'research_group', 'experiment')
        # if group == 'control':
        #     srl_prompts = [
        #         "What is your learning goal for this programming task?",
        #         "How do you plan to approach solving this problem?",
        #         "What strategies will you use to test and debug your code?",
        #         "Reflect on any errors: What caused them and how can you fix them?",
        #         "How does this task relate to what you've learned before?"
        #     ]
        #     return render_template('programming/programming_srl.html',
        #                            question=question, code=code, page_num=page_num,
        #                            timer_duration=timer_duration, srl_prompts=srl_prompts)
        # else:
        
        # Always use SRL AI assistant
        return render_template('programming/programming.html',
                               question=question, code=code, page_num=page_num,
                               timer_duration=timer_duration)
                          
    except Exception as e:
        print(f"Error in programming_question: {str(e)}")
        traceback.print_exc()
        flash('Error loading programming question', 'error')
        return render_template('programming/programming.html',
                               question={'question_text': 'Error loading question'},
                               code='', page_num=page_num)
    
@app.route('/programming/<page_num>/run', methods=['POST'])
@login_required
def programming_run(page_num):
    code = request.form.get('code')
    question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
    
    test_cases = question.get('test_cases', [])
    test_results = run_code_with_test_cases(code, test_cases)
    
    mongo.db.run_attempts.insert_one({
        'user_id': current_user.id,
        'question_id': f'programming_q{page_num}',
        'code': code,
        'test_results': test_results,
        'timestamp': datetime.datetime.utcnow()
    })
    
    return render_template('programming/programming.html',
                           question=question, code=code, page_num=page_num,
                           test_results=test_results)

@app.route('/programming/<page_num>/submit', methods=['POST'])
@login_required
def programming_submit(page_num):
    try:
        code = request.form.get('code')
        question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
        
        if not question:
            flash('Question not found', 'error')
            return redirect(url_for('programming_question', page_num=page_num))
        
        test_cases = question.get('test_cases', [])
        test_results = run_code_with_test_cases(code, test_cases)
        
        total_tests = len(test_results)
        passed_tests = sum(1 for result in test_results if result['status'] == 'passed')
        score = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        passed_all = (passed_tests == total_tests) and total_tests > 0
        
        submission = {
            'user_id': current_user.id,
            'question_id': f'programming_q{page_num}',
            'code': code,
            'test_results': test_results,
            'score': score,
            'timestamp': datetime.datetime.now(datetime.timezone.utc)
        }
        
        mongo.db.submissions.update_one(
            {'user_id': current_user.id, 'question_id': f'programming_q{page_num}'},
            {'$set': submission},
            upsert=True
        )
        
        # ✅ Track success for analytics
        track_user_success(current_user.id, f'programming_q{page_num}', passed_all, score, test_results)
        
        track_activity_end(current_user.id, f'programming_q{page_num}')
        
        # ✅ ALWAYS GO TO POST-SURVEY (FOR SINGLE QUESTION STUDY)
        flash('Submission complete. Please complete the post-survey.', 'success')
        return redirect(url_for('postsurvey'))
        
    except Exception as e:
        print("Error in submit:", str(e))
        traceback.print_exc()
        flash('Error submitting solution', 'error')
        # ✅ Even on error, redirect to post-survey
        return redirect(url_for('postsurvey'))



@app.route('/postSurvey', methods=['GET', 'POST'])
@login_required
def postsurvey():
    if request.method == 'GET':
        track_activity_start(current_user.id, 'postsurvey')
        questions = list(mongo.db.postSurveyQuestion.find())
        return render_template('surveys/postSurvey.html', questions=questions)
    
    elif request.method == 'POST':
        try:
            user_id = current_user.id
            user_name = current_user.name
            questions = list(mongo.db.postSurveyQuestion.find())
            
            answers = {}
            for question in questions:
                key = f"question_{question['_id']}"
                answer = request.form.get(key)
                if answer:
                    answers[key] = answer
            
            if len(answers) != len(questions):
                flash("Please answer all questions.", "error")
                return render_template('surveys/postSurvey.html', questions=questions, answers=answers)
            
            submission = {
                'user_id': user_id,
                'user_name': user_name,
                'answers': answers,
                'submitted_at': datetime.datetime.now(datetime.timezone.utc)
            }
            
            mongo.db.postSurveyAnswers.insert_one(submission)
            track_activity_end(current_user.id, 'postsurvey')
            
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {'completed': True, 'completion_date': datetime.datetime.now(datetime.timezone.utc)}}
            )
            
            flash("Thank you for completing the survey!")
            return redirect(url_for('completion_page'))
            
        except Exception as e:
            print("Error in postSurvey:", str(e))
            traceback.print_exc()
            flash("An error occurred. Please try again.")
            return render_template('surveys/postSurvey.html', questions=questions)

@app.route('/completion')
@login_required
def completion_page():
    return render_template('completion.html', 
                           user_name=current_user.name,
                           now=datetime.datetime.now())

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

# ============= JWT Token Handlers =============
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({'status': 'error', 'message': 'Token has expired'}), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({'status': 'error', 'message': 'Invalid token'}), 401

@jwt.unauthorized_loader
def unauthorized_callback(error):
    return jsonify({'status': 'error', 'message': 'Missing authorization token'}), 401

# ============= API Routes =============
@api_bp.route('/check-token', methods=['GET'])
@jwt_required()
def check_token():
    current_user_id = get_jwt_identity()
    return jsonify({
        'status': 'success',
        'message': 'Token is valid',
        'user_id': current_user_id
    }), 200
@api_bp.route('/microsoft_login', methods=['POST'])
def microsoft_login():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No input data provided"}), 400
    
    email = data.get("email", "").lower()
    name = data.get("name")
    
    if not email or not name:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
    
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
            "research_group": "experiment"  # Always experiment
        }
        result = mongo.db.users.insert_one(new_user)
        user_id = str(result.inserted_id)
    
    # COMMENTED OUT: Random group assignment
    # try:
    #     user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    #     if 'research_group' not in user_data or not user_data['research_group']:
    #         group = random.choice(['experiment', 'control'])
    #         mongo.db.users.update_one(
    #             {'_id': ObjectId(user_id)},
    #             {'$set': {'research_group': group}}
    #         )
    #         mongo.db.user_activities.insert_one({
    #             'user_id': user_id,
    #             'activity': 'group_assignment',
    #             'group': group,
    #             'timestamp': datetime.datetime.utcnow()
    #         })
    # except Exception as e:
    #     print(f"Error assigning research group: {str(e)}")
    
    # Always set to experiment if missing
    try:
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        if 'research_group' not in user_data or not user_data['research_group']:
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {'research_group': 'experiment'}}
            )
    except Exception as e:
        print(f"Error setting research group: {str(e)}")
    
    _insert_login_log(email, user_id)
    access_token = create_access_token(identity=user_id, expires_delta=datetime.timedelta(hours=1))
    
    presurvey_submitted = mongo.db.preSurveyAnswers.find_one({'user_id': user_id}) is not None
    pq1_submitted = mongo.db.submissions.find_one({'user_id': user_id, 'question_id': 'programming_q1'}) is not None
    pq2_submitted = mongo.db.submissions.find_one({'user_id': user_id, 'question_id': 'programming_q2'}) is not None
    
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
        
        # COMMENTED OUT: Random group assignment
        # try:
        #     user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        #     if 'research_group' not in user_data or not user_data['research_group']:
        #         group = random.choice(['experiment', 'control'])
        #         mongo.db.users.update_one(
        #             {'_id': ObjectId(user_id)},
        #             {'$set': {'research_group': group}}
        #         )
        #         mongo.db.user_activities.insert_one({
        #             'user_id': user_id,
        #             'activity': 'group_assignment',
        #             'group': group,
        #             'timestamp': datetime.datetime.utcnow()
        #         })
        # except Exception as e:
        #     print(f"Error assigning research group: {str(e)}")
        
        # Always set to experiment
        try:
            user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if 'research_group' not in user_data or not user_data['research_group']:
                mongo.db.users.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$set': {'research_group': 'experiment'}}
                )
        except Exception as e:
            print(f"Error setting research group: {str(e)}")
        
        _insert_login_log(email, user_id)
        access_token = create_access_token(identity=user_id, expires_delta=datetime.timedelta(days=1))
        
        presurvey_submitted = mongo.db.preSurveyAnswers.find_one({'user_id': user_id}) is not None
        pq1_submitted = mongo.db.submissions.find_one({'user_id': user_id, 'question_id': 'programming_q1'}) is not None
        pq2_submitted = mongo.db.submissions.find_one({'user_id': user_id, 'question_id': 'programming_q2'}) is not None
        
        return jsonify({
            "status": "success",
            "message": "Login successful!",
            "access_token": access_token,
            "user": {
                "id": user_id,
                "name": user.get("name"),
                "email": user.get("email"),
                'research_group': 'experiment'  # Always experiment
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
    
    # Validate email
    is_valid, message = is_valid_email(email)
    if not is_valid:
        return jsonify({'status': 'error', 'message': message}), 400
    
    existing_user = mongo.db.users.find_one({'email': email})
    if existing_user:
        return jsonify({'status': 'error', 'message': 'Email already exists. Please login.'}), 400
    
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    user = {
        'name': name,
        'email': email,
        'password': hashed_password.decode('utf-8'),
        'research_group': 'experiment'
    }
    result = mongo.db.users.insert_one(user)
    new_user = mongo.db.users.find_one({'_id': result.inserted_id})
    
    mongo.db.user_activities.insert_one({
        'user_id': str(result.inserted_id),
        'activity': 'group_assignment',
        'group': 'experiment',
        'timestamp': datetime.datetime.utcnow()
    })
    
    return jsonify({
        'status': 'success',
        'message': 'Registration successful!',
        'user': {
            'id': str(new_user['_id']),
            'name': new_user['name'],
            'email': new_user['email'],
            'research_group': 'experiment'
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
    
    new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    mongo.db.users.update_one(
        {'email': email},
        {'$set': {'password': hashed_password}}
    )
    
    msg = Message("Your New Password", sender=app.config['MAIL_USERNAME'], recipients=[email])
    msg.body = f"Your new password is: {new_password}"
    mail.send(msg)
    
    return jsonify({'status': 'success', 'message': 'New password sent to your email'})

@api_bp.route('/presurvey', methods=['GET', 'POST'])
@jwt_required()
def api_presurvey():
    current_user_id = get_jwt_identity()
    
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
            'submitted_at': datetime.datetime.now(datetime.timezone.utc)
        }
        
        mongo.db.preSurveyAnswers.insert_one(submission)
        track_activity_end(current_user_id, 'presurvey')
        
        return jsonify({'status': 'success', 'message': 'Survey submitted successfully'})

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
        
        if 'test_cases' in question:
            for tc in question['test_cases']:
                if '_id' in tc:
                    tc['_id'] = str(tc['_id'])
                    
        return jsonify({'status': 'success', 'question': question})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/programming/<page_num>', methods=['GET'])
@jwt_required()
def programming_question_api(page_num):
    try:
        current_user_id = get_jwt_identity()
        question_id = f'programming_q{page_num}'
        
        track_activity_start(current_user_id, question_id)
        
        question = mongo.db.programmingQuestions.find_one({'question_id': question_id})
        if not question:
            return jsonify({'status': 'error', 'message': 'Programming question not found.'}), 404
        
        # Check if multi-file question
        file_structure = question.get('file_structure')
        
        if file_structure and file_structure.get('type') == 'multi-file':
            # Multi-file mode (C++ only)
            files = []
            for file_info in file_structure['files']:
                filename = file_info['filename']
                
                autosaved = mongo.db.code_autosaves.find_one(
                    {
                        'user_id': current_user_id,
                        'question_id': question_id,
                        'filename': filename
                    },
                    sort=[('saved_at', -1)]
                )
                
                if autosaved and autosaved.get('code'):
                    code = autosaved['code']
                else:
                    code = file_info.get('starter_code', '')
                
                files.append({
                    'filename': filename,
                    'code': code,
                    'editable': file_info.get('editable', True)
                })
            
            return jsonify({
                'status': 'success',
                'question': {
                    'question_id': question.get('question_id'),
                    'question_text': question.get('question_text'),
                    'language': 'cpp',  # Force C++ only
                    'file_structure': {
                        'type': 'multi-file',
                        'files': files
                    }
                },
                'page_num': page_num,
                'timer_duration': 30
            })
        
        else:
            # Single file mode (C++ only)
            code = None
            autosaved = mongo.db.code_autosaves.find_one(
                {'user_id': current_user_id, 'question_id': question_id},
                sort=[('saved_at', -1)]
            )
            
            if autosaved and (autosaved.get('code') or '').strip():
                code = autosaved['code']
            else:
                submitted = mongo.db.submissions.find_one(
                    {'user_id': current_user_id, 'question_id': question_id}
                )
                if submitted and (submitted.get('code') or '').strip():
                    code = submitted['code']
                else:
                    code = question.get('starter_code', '') or ''
            
            if isinstance(code, str) and "\\n" in code and "\n" not in code:
                code = code.replace("\\n", "\n").replace("\\t", "\t")
            
            timer_duration = 30
            
            return jsonify({
                'status': 'success',
                'question': {
                    'question_id': question.get('question_id'),
                    'question_text': question.get('question_text'),
                    'starter_code': question.get('starter_code', '')
                },
                'code': code,
                'page_num': page_num,
                'timer_duration': timer_duration,
                'language': 'cpp'  # Force C++ only
            })
            
    except Exception as e:
        print(f"Error in programming_question: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Error loading programming question'}), 500

@api_bp.route('/programming/<page_num>/autosave', methods=['POST'])
@jwt_required()
def autosave_code(page_num):
    try:
        current_user_id = get_jwt_identity()
        data = request.json
        
        # Check if multi-file submission
        if 'files' in data:
            # Multi-file autosave
            for file_data in data['files']:
                filename = file_data.get('filename')
                code = file_data.get('code')
                
                autosave_doc = {
                    'user_id': current_user_id,
                    'question_id': f'programming_q{page_num}',
                    'filename': filename,
                    'code': code,
                    'language': 'cpp',
                    'saved_at': datetime.datetime.utcnow()
                }
                mongo.db.code_autosaves.insert_one(autosave_doc)
            
            return jsonify({'status': 'success', 'message': 'All files auto-saved'})
        
        else:
            # Single file autosave (existing logic)
            code = data.get('code')
            language = (data.get('language') or 'cpp').lower()
            
            autosave_doc = {
                'user_id': current_user_id,
                'question_id': f'programming_q{page_num}',
                'code': code,
                'language': language,
                'saved_at': datetime.datetime.utcnow()
            }
            mongo.db.code_autosaves.insert_one(autosave_doc)
            return jsonify({'status': 'success', 'message': 'Code auto-saved'})
            
    except Exception as e:
        print(f"Autosave error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/programming/<page_num>/run', methods=['POST'])
@jwt_required()
def programming_run_api(page_num):
    current_user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    # Check if multi-file submission
    if 'files' in data:
        # Multi-file execution (C++ only)
        files_dict = {f['filename']: f['code'] for f in data['files']}
        input_data = data.get('input', '')
        
        resp = run_cpp_multifile(files_dict, input_data=input_data)
        
        if resp["status"] == "ok":
            combined = ((resp.get("stdout") or "") + ("\n" + resp.get("stderr") if resp.get("stderr") else "")).strip()
            
            mongo.db.run_attempts.insert_one({
                'user_id': current_user_id,
                'question_id': f'programming_q{page_num}',
                'files': files_dict,
                'language': 'cpp',
                'output': combined,
                'timestamp': datetime.datetime.utcnow()
            })
            
            return jsonify({'status': 'success', 'output': combined, 'language': 'cpp'})
        else:
            err = resp.get("stderr") or resp.get("stdout") or resp.get("status")
            return jsonify({'status': 'error', 'message': err, 'language': 'cpp'}), 400
    
    else:
        # Single file execution (C++ only)
        code = data.get('code')
        language = 'cpp'  # Force C++ only
        input_data = data.get('input', '')
        
        if not code.strip():
            return jsonify({'status': 'error', 'message': 'Code is required'}), 400
        
        resp = run_cpp_once(code, input_data=input_data)
        
        if resp["status"] == "ok":
            combined = ((resp.get("stdout") or "") + ("\n" + resp.get("stderr") if resp.get("stderr") else "")).strip()
            
            mongo.db.run_attempts.insert_one({
                'user_id': current_user_id,
                'question_id': f'programming_q{page_num}',
                'code': code,
                'language': language,
                'output': combined,
                'timestamp': datetime.datetime.utcnow()
            })
            
            return jsonify({'status': 'success', 'output': combined, 'language': language})
        else:
            err = resp.get("stderr") or resp.get("stdout") or resp.get("status")
            return jsonify({'status': 'error', 'message': err, 'language': language}), 400

@api_bp.route('/programming/<page_num>/submit', methods=['POST'])
@jwt_required()
def programming_submit_api(page_num):
    current_user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    question = mongo.db.programmingQuestions.find_one({'question_id': f'programming_q{page_num}'})
    if not question:
        return jsonify({'status': 'error', 'message': 'Question not found'}), 404
    
    # Check if multi-file submission
    if 'files' in data:
        files_dict = {f['filename']: f['code'] for f in data['files']}
        test_cases = question.get('test_cases', [])
        
        test_results = run_code_with_test_cases_multifile('cpp', files_dict, test_cases)
        
        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results if r.get('status') == 'passed')
        score = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        passed_all = (passed_tests == total_tests) and total_tests > 0
        
        submission = {
            'user_id': current_user_id,
            'question_id': f'programming_q{page_num}',
            'language': 'cpp',
            'files': files_dict,
            'test_results': test_results,
            'score': score,
            'timestamp': datetime.datetime.now(datetime.timezone.utc)
        }
        
        mongo.db.submissions.update_one(
            {'user_id': current_user_id, 'question_id': f'programming_q{page_num}'},
            {'$set': submission},
            upsert=True
        )
        
        track_user_success(current_user_id, f'programming_q{page_num}', passed_all, score, test_results)
        track_activity_end(current_user_id, f'programming_q{page_num}')
        
        # ✅ ALWAYS GO TO POST-SURVEY (SINGLE QUESTION STUDY)
        return jsonify({
            'status': 'success',
            'message': 'Submission saved',
            'score': score,
            'test_results': test_results,
            'passed_all_tests': passed_all,
            'next_action': 'postsurvey'
        })
    
    else:
        # Single file submission (C++ only)
        code = data.get('code')
        language = 'cpp'
        
        if not code:
            return jsonify({'status': 'error', 'message': 'No code provided'}), 400
        
        test_cases = question.get('test_cases', [])
        test_results = run_code_with_test_cases_multi(language, code, test_cases)
        
        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results if r.get('status') == 'passed')
        score = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        passed_all = (passed_tests == total_tests) and total_tests > 0
        
        submission = {
            'user_id': current_user_id,
            'question_id': f'programming_q{page_num}',
            'language': language,
            'code': code,
            'test_results': test_results,
            'score': score,
            'timestamp': datetime.datetime.now(datetime.timezone.utc)
        }
        
        mongo.db.submissions.update_one(
            {'user_id': current_user_id, 'question_id': f'programming_q{page_num}'},
            {'$set': submission},
            upsert=True
        )
        
        track_user_success(current_user_id, f'programming_q{page_num}', passed_all, score, test_results)
        track_activity_end(current_user_id, f'programming_q{page_num}')
        
        # ✅ ALWAYS GO TO POST-SURVEY (SINGLE QUESTION STUDY)
        return jsonify({
            'status': 'success',
            'message': 'Submission saved',
            'score': score,
            'test_results': test_results,
            'passed_all_tests': passed_all,
            'next_action': 'postsurvey'
        })


def response_contains_code(text):
    """Heuristic check: did the AI's reply leak actual code despite SRL_SYSTEM_CORE
    telling it never to? The system prompt is not a hard guarantee -- this is the
    server-side backstop, since for this study a silent violation isn't just a UX
    problem, it's a validity problem (it changes what's actually being measured)."""
    if not text:
        return False
    if '```' in text:
        return True
    cpp_signals = [r'#include\s*<', r'\bint\s+main\s*\(', r'\bstd::\w+', r'\bcout\s*<<', r'\bcin\s*>>']
    if any(re.search(pat, text) for pat in cpp_signals):
        return True
    # A couple of semicolon-terminated lines is a strong code signal; one on its own
    # is too common in ordinary prose to flag alone.
    if len(re.findall(r';\s*$', text, re.MULTILINE)) >= 2:
        return True
    return False


@api_bp.route('/programming/<page_num>/prompt', methods=['POST'])
@jwt_required()
def programming_prompt_api(page_num):
    """Natural SRL-based conversational AI - Always enabled"""
    current_user_id = get_jwt_identity()

    data = request.get_json()
    prompt = data.get('prompt', '')
    code = data.get('code', '')
    terminal_output = data.get('terminal_output', '')
    hide_user_prompt = data.get('hide_user_prompt', False)

    try:
        # Moderation check on the incoming prompt before it reaches the model or gets
        # logged anywhere -- cheap (OpenAI's moderation endpoint is free) and this is
        # about to be public, so anyone can reach it, not just enrolled students.
        try:
            moderation = client.moderations.create(input=prompt)
            if moderation.results[0].flagged:
                mongo.db.moderation_flags.insert_one({
                    'user_id': current_user_id,
                    'question_id': f'programming_q{page_num}',
                    'prompt': prompt,
                    'categories': [c for c, v in moderation.results[0].categories.model_dump().items() if v],
                    'timestamp': datetime.datetime.utcnow()
                })
                return jsonify({
                    'status': 'success',
                    'ai_response': "Let's keep our conversation focused on the programming task -- what part of the problem can I help you think through?",
                    'phase': 'PLANNING',
                    'step_info': {'step_number': 0, 'total_steps': 3}
                })
        except Exception as mod_err:
            # Don't let a moderation-API hiccup block a legitimate student -- log and
            # continue to the real request instead of failing closed.
            print(f"Moderation check failed (continuing without it): {mod_err}")

        question_id = f'programming_q{page_num}'
        question = mongo.db.programmingQuestions.find_one({'question_id': question_id})
        question_text = question.get('question_text', '') if question else ''
        
        latest_run = mongo.db.run_attempts.find_one(
            {'user_id': current_user_id, 'question_id': question_id},
            sort=[('timestamp', -1)]
        )
        latest_test_results = format_test_results(latest_run.get('test_results', [])) if latest_run else ""
        
        if not terminal_output and latest_test_results:
            terminal_output = latest_test_results
        
        srl_state = SRLConversationManager.get_or_create_state(current_user_id, question_id)
        
        conversation = mongo.db.conversations.find_one({
            'user_id': current_user_id,
            'question_id': question_id
        })
        history = conversation.get('history', []) if conversation else []
        
        current_step_info = {
            'step_number': srl_state.get('step_number', 0),
            'total_steps': srl_state.get('total_steps', 3),
            'step_name': srl_state.get('current_step_name', 'Getting started')
        }
        
        system_prompt = build_natural_srl_prompt(
            question_text, code, terminal_output, history, current_step_info
        )
        
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in history[-8:]:
            messages.append({"role": msg['role'], "content": msg['content']})
        
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=600
        )
        
        ai_response = response.choices[0].message.content

        # Server-side backstop for the "never write solution code" rule: the system
        # prompt asks for this, but that's not a guarantee against an adversarial or
        # just persistent user. One retry with a stricter reminder; if that also
        # leaks code, fall back to a fixed refusal rather than show it.
        guardrail_violation = response_contains_code(ai_response)
        if guardrail_violation:
            retry_messages = messages + [
                {"role": "assistant", "content": ai_response},
                {"role": "system", "content": (
                    "Your previous reply included code, which breaks the ABSOLUTE RULES above. "
                    "Rewrite it with no code at all -- no fenced blocks, no snippets, no syntax "
                    "examples in this problem's language. Use a plain-language analogy instead."
                )}
            ]
            retry_response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=retry_messages,
                temperature=0.5,
                max_tokens=600
            )
            retry_text = retry_response.choices[0].message.content
            if response_contains_code(retry_text):
                ai_response = (
                    "I can't share code here -- my role is to coach your process, not write it "
                    "for you. Let's break this down conceptually instead. What part are you stuck on?"
                )
            else:
                ai_response = retry_text

            mongo.db.guardrail_violations.insert_one({
                'user_id': current_user_id,
                'question_id': question_id,
                'user_prompt': prompt,
                'timestamp': datetime.datetime.utcnow()
            })

        detected_phase = detect_srl_phase_from_conversation(
            ai_response, prompt, code, terminal_output, srl_state.get('phase', 'PLANNING')
        )
        
        step_match = re.search(r'Step (\d+)', ai_response)
        if step_match:
            step_num = int(step_match.group(1))
            if step_num > current_step_info['step_number']:
                current_step_info['step_number'] = step_num
        
       
        if not hide_user_prompt:
            history.append({"role": "user", "content": prompt})
        
        # ✅ Always save AI response
        history.append({"role": "assistant", "content": ai_response})
        
        SRLConversationManager.update_state(current_user_id, question_id, {
            'interaction_count': srl_state.get('interaction_count', 0) + 1,
            'phase': detected_phase,
            'step_number': current_step_info['step_number']
        })
        
        mongo.db.conversations.update_one(
            {'user_id': current_user_id, 'question_id': question_id},
            {'$set': {'history': history}},
            upsert=True
        )
        
        mongo.db.ai_interactions.insert_one({
            'user_id': current_user_id,
            'question_id': question_id,
            'group': 'experiment',
            'phase': detected_phase,
            'prompt': '[AUTO_START]' if hide_user_prompt else prompt,
            'ai_response': ai_response,
            'code_length': len(code) if code else 0,
            'has_output': bool(terminal_output),
            'timestamp': datetime.datetime.utcnow()
        })
        
        return jsonify({
            'status': 'success',
            'ai_response': ai_response,
            'phase': detected_phase,
            'step_info': current_step_info
        })
        
    except Exception as e:
        print(f"Error in programming_prompt: {str(e)}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Error: {str(e)}'}), 500




@api_bp.route('/programming/<page_num>/feedback', methods=['POST'])
@jwt_required()
def log_feedback(page_num):
    """Log thumbs up/down feedback"""
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    helpful = data.get('helpful', None)
    phase = data.get('phase', 'Unknown')
    message_index = data.get('message_index', -1)
    message_content = data.get('message_content', '')
    
    try:
        question_id = f'programming_q{page_num}'
        
        mongo.db.user_feedback.insert_one({
            'user_id': current_user_id,
            'question_id': question_id,
            'phase': phase,
            'helpful': helpful,
            'message_index': message_index,
            'message_content': message_content[:200],
            'timestamp': datetime.datetime.utcnow()
        })
        
        return jsonify({'status': 'success', 'message': 'Feedback recorded'})
        
    except Exception as e:
        print(f"Error logging feedback: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/programming/<page_num>/conversation_state', methods=['GET'])
@jwt_required()
def get_conversation_state(page_num):
    """Get current conversation state"""
    current_user_id = get_jwt_identity()
    question_id = f'programming_q{page_num}'
    
    try:
        srl_state = SRLConversationManager.get_or_create_state(current_user_id, question_id)
        
        conversation = mongo.db.conversations.find_one({
            'user_id': current_user_id,
            'question_id': question_id
        })
        
        return jsonify({
            'status': 'success',
            'phase': srl_state.get('phase', 'PLANNING'),
            'step_info': {
                'current': srl_state.get('step_number', 0),
                'total': srl_state.get('total_steps', 3),
                'step_name': srl_state.get('current_step_name', '')
            },
            'conversation_history': conversation.get('history', []) if conversation else [],
            'interaction_count': srl_state.get('interaction_count', 0)
        })
        
    except Exception as e:
        print(f"Error getting conversation state: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/programming/<page_num>/detect_phase', methods=['POST'])
@jwt_required()
def detect_srl_phase(page_num):
    """Intelligent SRL phase detection based on user's prompt"""
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    user_prompt = data.get('prompt', '')
    code = data.get('code', '')
    terminal_output = data.get('terminal_output', '')
    
    if not user_prompt.strip():
        return jsonify({'status': 'error', 'message': 'Prompt is required'}), 400
    
    try:
        question_id = f'programming_q{page_num}'
        question = mongo.db.programmingQuestions.find_one({'question_id': question_id})
        question_text = question.get('question_text', 'No question available') if question else 'No question available'
        
        detection_prompt = f"""You are an expert educational AI that detects which Self-Regulated Learning (SRL) phase a student is in based on their question.

Analyze the student's question and determine which phase they're in:

**PLANNING Phase** - Student is:
- Asking "what is", "how do I", "explain", "syntax"
- Learning new concepts before coding
- Asking about structure, approach, or starting point

**MONITORING Phase** - Student is:
- Saying "stuck", "error", "not working", "bug", "crashes"
- Debugging active code
- Has written code but it's not working correctly

**REFLECTION Phase** - Student is:
- Saying "finished", "done", "completed", "works"
- Asking "how can I improve", "is this efficient"
- Reviewing completed code

**Student's question:** "{user_prompt}"
**Context:**
- Programming task: {question_text}
- Current code: {code if code.strip() else 'No code written yet'}
- Terminal output: {terminal_output if terminal_output.strip() else 'No output yet'}

**Your response must be EXACTLY in this JSON format:**
{{
    "phase": "Planning" or "Monitoring" or "Reflection",
    "confidence": "high" or "medium" or "low",
    "explanation": "One sentence explaining why"
}}

Respond ONLY with valid JSON, nothing else."""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert in Self-Regulated Learning theory. Always respond with valid JSON only."},
                {"role": "user", "content": detection_prompt}
            ],
            temperature=0.3,
        )
        
        ai_response = response.choices[0].message.content.strip()
        
        try:
            if ai_response.startswith('```'):
                ai_response = ai_response.split('```')[1]
                if ai_response.startswith('json'):
                    ai_response = ai_response[4:]
            
            detection_result = json.loads(ai_response)
            detected_phase = detection_result.get('phase', 'Planning')
            confidence = detection_result.get('confidence', 'medium')
            
        except json.JSONDecodeError:
            user_prompt_lower = user_prompt.lower()
            
            planning_keywords = ['what', 'how', 'syntax', 'explain', 'start', 'begin', 'understand']
            monitoring_keywords = ['error', 'bug', 'stuck', 'not working', 'crash', 'wrong', 'issue']
            reflection_keywords = ['improve', 'better', 'optimize', 'efficient', 'finished', 'done', 'works']
            
            planning_score = sum(1 for keyword in planning_keywords if keyword in user_prompt_lower)
            monitoring_score = sum(1 for keyword in monitoring_keywords if keyword in user_prompt_lower)
            reflection_score = sum(1 for keyword in reflection_keywords if keyword in user_prompt_lower)
            
            if monitoring_score > planning_score and monitoring_score > reflection_score:
                detected_phase = 'Monitoring'
            elif reflection_score > planning_score and reflection_score > monitoring_score:
                detected_phase = 'Reflection'
            else:
                detected_phase = 'Planning'
            
            confidence = 'medium'
        
        phase_explanation = f"Based on your question, I can see you're in the **{detected_phase}** phase.\n\n"
        
        if detected_phase == 'Planning':
            phase_explanation += "This means you're working on understanding concepts and planning your approach. Let me help you build a strong foundation!"
        elif detected_phase == 'Monitoring':
            phase_explanation += "This means you're actively working on your code and need help tracking your progress. Let me help you get unstuck!"
        else:
            phase_explanation += "This means you're reviewing your work and thinking about improvements. Let me help you reflect on what you've accomplished!"
        
        mongo.db.phase_detections.insert_one({
            'user_id': current_user_id,
            'question_id': question_id,
            'user_prompt': user_prompt,
            'detected_phase': detected_phase,
            'confidence': confidence,
            'timestamp': datetime.datetime.utcnow()
        })
        
        return jsonify({
            'status': 'success',
            'detected_phase': detected_phase,
            'confidence': confidence,
            'phase_explanation': phase_explanation
        })
        
    except Exception as e:
        print(f"Error in phase detection: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'status': 'success',
            'detected_phase': 'Planning',
            'confidence': 'low',
            'phase_explanation': "Let me help you with planning."
        })

@api_bp.route('/programming/<page_num>/confidence', methods=['POST'])
@jwt_required()
def record_confidence_rating(page_num):
    """Record student confidence during monitoring phase"""
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    rating = data.get('rating')
    step_number = data.get('step_number')
    
    if not rating:
        return jsonify({'status': 'error', 'message': 'Rating is required'}), 400
    
    try:
        question_id = f'programming_q{page_num}'
        srl_state = SRLConversationManager.get_or_create_state(current_user_id, question_id)
        
        confidence_ratings = srl_state.get('confidence_ratings', [])
        confidence_ratings.append({
            'rating': int(rating),
            'step': step_number or srl_state['step_number'],
            'timestamp': datetime.datetime.utcnow()
        })
        
        SRLConversationManager.update_state(current_user_id, question_id, {
            'confidence_ratings': confidence_ratings
        })
        
        return jsonify({'status': 'success', 'message': 'Confidence recorded'})
        
    except Exception as e:
        print(f"Error recording confidence: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/postSurvey', methods=['GET', 'POST'])
@jwt_required()
def api_postsurvey():
    user_id = get_jwt_identity()
    
    if request.method == 'GET':
        track_activity_start(user_id, 'postsurvey')
        questions = list(mongo.db.postSurveyQuestion.find({}))
        for question in questions:
            question['id'] = str(question['_id'])
            del question['_id']
        return jsonify({'questions': questions})
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'status': 'error', 'message': 'No data provided'}), 400
            
            questions = list(mongo.db.postSurveyQuestion.find())
            answers = {}
            
            for question in questions:
                key = f"question_{question['_id']}"
                answer = data.get(key)
                if answer:
                    answers[key] = answer
            
            if len(answers) != len(questions):
                return jsonify({'status': 'error', 'message': 'Please answer all questions'}), 400
            
            submission = {
                'user_id': user_id,
                'answers': answers,
                'submitted_at': datetime.datetime.now(datetime.timezone.utc)
            }
            
            mongo.db.postSurveyAnswers.insert_one(submission)
            track_activity_end(user_id, 'postsurvey')
            
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {'completed': True, 'completion_date': datetime.datetime.now(datetime.timezone.utc)}}
            )
            
            return jsonify({'status': 'success', 'message': 'Survey submitted successfully'})
        
        except Exception as e:
            print("Error in postSurvey:", str(e))
            traceback.print_exc()
            return jsonify({'status': 'error', 'message': 'An error occurred'}), 500

@api_bp.route('/completion', methods=['GET'])
@jwt_required()
def api_completion():
    try:
        user_id = get_jwt_identity()
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
        data = request.get_json()
        code = data.get('code')
        
        if not code.strip():
            return jsonify({'status': 'error', 'message': 'Code is empty'}), 400
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        process = subprocess.Popen(
            ['python3', temp_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(timeout=10)
        os.unlink(temp_file)
        
        return jsonify({
            'status': 'success',
            'stdout': stdout.strip(),
            'stderr': stderr.strip()
        })
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'error', 'stderr': 'Execution timed out (10 seconds)'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'stderr': str(e)}), 500

# Register blueprint
app.register_blueprint(api_bp, url_prefix='/api')

# Run application
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001, debug=True)