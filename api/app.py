import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import re
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///jobs.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'job-app-secret')
db = SQLAlchemy(app)


# Database Models
class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_title = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(50), nullable=False)
    job_url = db.Column(db.String(200), nullable=False, unique=True)
    status = db.Column(db.String(20), default='pending')
    match_score = db.Column(db.Float, default=0.0)
    applied_date = db.Column(db.DateTime, nullable=True)
    resume_version = db.Column(db.String(20), default='v1')
    created_at = db.Column(db.DateTime, default=db.func.now())


class JobPosting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(50), nullable=False)
    job_type = db.Column(db.String(20), nullable=False)  # onsite, remote, hybrid
    posted_date = db.Column(db.DateTime, nullable=False)
    source = db.Column(db.String(50), nullable=False)  # linkedin, indeed, rozee
    job_url = db.Column(db.String(200), nullable=False, unique=True)


# Skill extraction helper
def extract_skills(text):
    """Extract potential skills from text using keyword matching"""
    skill_keywords = [
        'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust', 'php',
        'react', 'angular', 'vue', 'node', 'express', 'django', 'flask', 'fastapi',
        'html', 'css', 'sql', 'mongodb', 'postgresql', 'mysql', 'oracle',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'git', 'jenkins',
        'machine learning', 'ai', 'data science', 'analytics',
        'project management', 'agile', 'scrum', 'leadership',
    ]
    
    found = set()
    text_lower = text.lower()
    for skill in skill_keywords:
        if skill in text_lower:
            found.add(skill)
    return found


def match_cv_to_job(cv_text, job_description):
    """Calculate match score between CV and job description"""
    cv_skills = extract_skills(cv_text)
    jd_skills = extract_skills(job_description)
    
    if not jd_skills:
        return 0.0, []
    
    matched = cv_skills & jd_skills
    score = (len(matched) / len(jd_skills)) * 100 if jd_skills else 0
    
    return round(min(score, 100), 2), list(matched)


# Routes
@app.route('/')
def index():
    applications = Application.query.order_by(Application.created_at.desc()).all()
    return render_template('index.html', applications=applications)


@app.route('/jobs')
def jobs():
    jobs = JobPosting.query.order_by(JobPosting.posted_date.desc()).all()
    return render_template('jobs.html', jobs=jobs)


@app.route('/api/match', methods=['POST'])
def api_match():
    data = request.get_json()
    cv_text = data.get('cv_text', '')
    job_description = data.get('job_description', '')
    
    score, matched_skills = match_cv_to_job(cv_text, job_description)
    jd_skills = extract_skills(job_description)
    
    return jsonify({
        'match_score': score,
        'matched_skills': matched_skills,
        'cv_skills': list(extract_skills(cv_text)),
        'jd_skills': list(jd_skills)
    })


@app.route('/apply/<int:job_id>')
def apply_job(job_id):
    from datetime import datetime
    job = JobPosting.query.get_or_404(job_id)
    
    # Match CV against job description
    score, matched = match_cv_to_job('', job.description)
    resume_version = 'v1'
    
    # Update or create application
    existing = Application.query.filter_by(job_url=job.job_url).first()
    if existing:
        existing.match_score = score
        existing.resume_version = resume_version
        existing.status = 'pending'
    else:
        existing = Application(
            job_title=job.title,
            company=job.company,
            location=job.location,
            job_url=job.job_url,
            match_score=score,
            resume_version=resume_version,
            status='pending'
        )
        db.session.add(existing)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'match_score': score,
        'matched_skills': matched,
        'resume_version': resume_version,
        'job_title': job.title,
        'company': job.company
    })


# Import CVs from files at startup
def load_cvs():
    """Load CV texts from files in cvs directory"""
    cv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cvs')
    os.makedirs(cv_dir, exist_ok=True)
    
    cvs = {}
    if os.path.exists(cv_dir):
        for f in os.listdir(cv_dir):
            if f.endswith('.txt') or f.endswith('.pdf'):
                path = os.path.join(cv_dir, f)
                try:
                    with open(path, 'r', encoding='utf-8') as fh:
                        cvs[f] = fh.read()
                except:
                    pass
    return cvs


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    cvs = load_cvs()
    print(f"Loaded {len(cvs)} CV(s) for matching")
    
    # Port from environment variable for Vercel
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
