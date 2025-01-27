# Flask & MongoDB Learning Platform

## Features & Tasks

### Registration System
- [x] Create registration form with Flask-WTF
- [x] Add email validation on server side
- [x] Implement MongoDB user storage
- [x] Add Flask redirect to login

### Login System
- [x] Create login form
- [x] Add server-side authentication
- [ ] Implement password recovery via email
- [x] Add success redirect to pre-survey

### Pre-Survey Module
- [x] Create survey manoally in MongoDB
- [x] Set up answer storage in MongoDB

### Programming Assessment
- [ ] Create code submission form
- [ ] Add ChatGPT prompt submission
- [ ] Implement server-side code execution
- [ ] Add test case validation
- [ ] Create results display template
- [ ] Set up periodic code state saving
- [ ] Implement usage tracking

### Analytics & Feedback
- [ ] Create metrics collection system
- [ ] Implement comparison calculations
- [ ] Add results display templates

### Post-Survey Module
- [ ] Create post-survey forms
- [ ] Add question progression system
- [ ] Implement answer storage

## Technical Stack
- Backend: Flask
  - Flask-WTF for forms
  - Jinja2 templates
  - Flask-PyMongo
- Database: MongoDB
- Frontend: 
  - HTML
  - CSS
  - Flask template rendering

## Database Collections

- [x] **Users**  
  - `full_name`: String  
  - `email`: String  
  - `password`: String (hashed)
    
- [ ] **PreSurveyQuestion**  


- [ ] **PreSurveyAnswers**  
  - `user_id`: ObjectId  
  - `answers`: Array  
  - `timestamp`: DateTime

- [ ] **ProgrammingQ1Answers**  
  - `user_id`: ObjectId  
  - `code`: String  
  - `result`: Object  
  - `timestamp`: DateTime

- [ ] **FeedbackMatrix**  
  - `user_id`: ObjectId  
  - `metrics`: Object  
  - `comparison_data`: Object

- [ ] **PostSurveyAnswers**  
  - `user_id`: ObjectId  
  - `answers`: Array  
  - `timestamp`: DateTime

- [ ] **ProgrammingQ2Answers**  
  - `user_id`: ObjectId  
  - `code`: String  
  - `result`: Object  
  - `timestamp`: DateTime

- [ ] **Prompts**  
  - `user_id`: ObjectId  
  - `question_id`: ObjectId  
  - `prompt_text`: String  
  - `timestamp`: DateTime

- [ ] **AIResponses**  
  - `prompt_id`: ObjectId  
  - `response_text`: String  
  - `timestamp`: DateTime

- [ ] **UserMetrics**  
  - `user_id`: ObjectId  
  - `run_button_clicks`: Number  
  - `test_case_uses`: Number  
  - `code_snapshots`: Array of Objects  
    - `timestamp`: DateTime  
    - `code_state`: String

