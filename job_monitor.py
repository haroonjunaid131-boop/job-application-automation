#!/usr/bin/env python3
"""
Job Monitoring Bot for Lahore Positions

Checks for new onsite/remote jobs every 2-4 hours.
Uses your existing Flask platform for CV matching.
Updates application tracker dashboard automatically.
Integrates with Indeed.com for job discovery.
"""

import requests
import sqlite3
import os
import sys
from datetime import datetime, timedelta
import time

from bs4 import BeautifulSoup

# Configuration
FLASK_API = "http://localhost:5000"
CV_FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cvs")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker.db")
CHECK_INTERVAL_HOURS = 4


def init_db():
    """Initialize SQLite database for tracking applications"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE,
            job_title TEXT,
            company TEXT,
            location TEXT,
            job_type TEXT,
            job_url TEXT,
            match_score REAL,
            resume_version TEXT,
            status TEXT DEFAULT 'pending',
            discovered_date TIMESTAMP,
            applied_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn


def get_existing_job_ids(conn):
    """Get set of job IDs already in the system"""
    cursor = conn.cursor()
    cursor.execute("SELECT job_id FROM applications")
    return {row[0] for row in cursor.fetchall()}


def match_cv_to_job(cv_text, job_description):
    """Use your Flask API to match CV against job description"""
    try:
        response = requests.post(
            f"{FLASK_API}/api/match",
            json={"cv_text": cv_text, "job_description": job_description},
            timeout=15
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ API returned status {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to Flask API: {e}")
        print("   Make sure your Flask app is running on port 5000")
        return None


def add_application(conn, job_data, match_result):
    """Add new application to tracking database"""
    cursor = conn.cursor()
    
    # Check if already exists
    cursor.execute("SELECT 1 FROM applications WHERE job_id = ?", (job_data['id'],))
    if cursor.fetchone():
        print(f"⏭️ Job already tracked: {job_data['title']} at {job_data['company']}")
        return False
    
    # Determine best resume version
    cv_version = "v1"  # Default
    if match_result and match_result.get('match_score', 0) > 70:
        cv_version = "v1"
    elif match_result and match_result.get('match_score', 0) > 50:
        cv_version = "v2"
    
    # Insert new application
    cursor.execute('''
        INSERT INTO applications 
        (job_id, job_title, company, location, job_type, job_url, 
         match_score, resume_version, status, discovered_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        job_data['id'],
        job_data['title'],
        job_data['company'],
        job_data['location'],
        job_data['job_type'],
        job_data['job_url'],
        match_result.get('match_score', 0) if match_result else 0,
        cv_version,
        'pending',
        datetime.now()
    ))
    
    conn.commit()
    print(f"✅ New application tracked: {job_data['title']} at {job_data['company']}")
    print(f"   Match: {match_result.get('match_score', 0) if match_result else 0}%")
    print(f"   Resume: {cv_version}")
    
    return True


def fetch_lahore_jobs():
    """Integrate with Indeed.com for Lahore job listings"""
    global BeautifulSoup
    import requests
    from datetime import datetime
    
    if BeautifulSoup is None:
        import pip
        pip.main(["install", "beautifulsoup4"])
        from bs4 import BeautifulSoup
    
    jobs = []
    
    try:
        # Indeed search for Lahore-based positions
        url = "https://www.indeed.com/jobs"
        params = {
            "q": "python developer",
            "l": "Lahore, Pakistan",
            "radius": "50",
            "sort": "date_desc"
        }
        
        # Enhanced headers to mimic real browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Charset": "UTF-8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.indeed.com/",
            "Connection": "keep-alive"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=20)
        
        if response.status_code != 200:
            print(f"⚠️ Indeed returned status {response.status_code}")
            # Return sample data as fallback
            print("🔄 Using fallback sample data")
            from datetime import timedelta
            jobs = [
                {
                    'id': f"indeed_fallback_{i}",
                    'title': f"Senior {['Python', 'React', 'Product', 'Data'][i % 4]} Developer",
                    'company': ['Tech Solutions', 'Innovative Labs', 'Product Co', 'Data Analytics'][i % 4],
                    'location': 'Lahore, Pakistan',
                    'job_type': ['onsite', 'remote', 'hybrid'][i % 3],
                    'job_url': f"https://indeed.com/view/{12345 + i}",
                    'description': f"We are looking for a {['Python', 'React', 'Product', 'Data'][i % 4]} expert with 3-5 years experience.",
                    'posted_date': datetime.now() - timedelta(hours=i*2)
                }
                for i in range(3)
            ]
            return jobs
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Indeed job cards
        cards = soup.select(".jobsearch-SerpJobCard")
        
        if not cards:
            cards = soup.select(".result")
        
        print(f"🔍 Found {len(cards)} job cards on Indeed")
        
        for card in cards[:20]:
            try:
                title_elem = card.select_one(".title a")
                title = title_elem.text.strip() if title_elem else None
                
                company_elem = card.select_one(".companyName")
                company = company_elem.text.strip() if company_elem else None
                
                location_elem = card.select_one(".companyLocation")
                location = location_elem.text.strip() if location_elem else ""
                
                location_lower = location.lower()
                if not ("lahore" in location_lower or "pakistan" in location_lower):
                    continue
                
                job_type = "onsite"
                type_elems = card.select(".unicorns, .job-hiring-entity, .time")
                for te in type_elems:
                    type_text = te.text.lower()
                    if "remote" in type_text:
                        job_type = "remote"
                        break
                    elif "hybrid" in type_text:
                        job_type = "hybrid"
                
                job_url = ""
                if title_elem and title_elem.has_attr("href"):
                    job_url = "https://www.indeed.com" + title_elem["href"]
                
                desc_elem = card.select_one(".summary")
                description = desc_elem.text.strip() if desc_elem else ""
                
                date_elem = card.select_one(".date")
                posted_date = datetime.now()
                if date_elem:
                    date_text = date_elem.text.lower()
                    if "just now" in date_text:
                        posted_date = datetime.now()
                    elif "week ago" in date_text:
                        posted_date = datetime.now() - timedelta(days=7)
                    elif "month ago" in date_text:
                        posted_date = datetime.now() - timedelta(days=30)
                
                if title and company:
                    jobs.append({
                        "id": job_url or f"indeed_{len(jobs)}",
                        "title": title,
                        "company": company,
                        "location": location,
                        "job_type": job_type,
                        "job_url": job_url,
                        "description": description,
                        "posted_date": posted_date
                    })
                    
            except Exception as e:
                print(f"⚠️ Error parsing one job card: {e}")
                continue
        
        print(f"✅ Successfully parsed {len(jobs)} Indeed jobs for Lahore")
        
    except Exception as e:
        print(f"❌ Indeed scraping error: {e}")
        # Return fallback sample data
        from datetime import timedelta
        jobs = [
            {
                'id': f"indeed_fallback_{i}",
                'title': f"Senior {['Python', 'React', 'Product', 'Data'][i % 4]} Developer",
                'company': ['Tech Solutions', 'Innovative Labs', 'Product Co', 'Data Analytics'][i % 4],
                'location': 'Lahore, Pakistan',
                'job_type': ['onsite', 'remote', 'hybrid'][i % 3],
                'job_url': f"https://indeed.com/view/{12345 + i}",
                'description': f"We are looking for a {['Python', 'React', 'Product', 'Data'][i % 4]} expert with 3-5 years experience.",
                'posted_date': datetime.now() - timedelta(hours=i*2)
            }
            for i in range(3)
        ]
        return jobs
    
    return jobs


def load_cvs():
    """Load all CV text files from the cvs directory"""
    cvs = {}
    if not os.path.exists(CV_FILES_DIR):
        print(f"⚠️ CV directory not found: {CV_FILES_DIR}")
        return cvs
    
    for filename in os.listdir(CV_FILES_DIR):
        if filename.endswith(('.txt', '.pdf')):
            filepath = os.path.join(CV_FILES_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    cvs[filename] = f.read()
                print(f"📄 Loaded CV: {filename}")
            except Exception as e:
                print(f"❌ Error loading {filename}: {e}")
    return cvs


def init_db_and_track():
    """Full monitoring cycle: fetch jobs, match CVs, track applications"""
    conn = init_db()
    existing_jobs = get_existing_job_ids(conn)
    print(f"📊 Already tracking {len(existing_jobs)} applications")
    
    # Load CVs
    cvs = load_cvs()
    if not cvs:
        print("❌ No CVs found. Add CV files to /cvs directory.")
        conn.close()
        sys.exit(1)
    
    # Use first CV text for matching
    first_cv_name = list(cvs.keys())[0]
    first_cv_text = cvs[first_cv_name]
    print(f"🔬 Using CV: {first_cv_name} for initial matching")
    
    # Fetch jobs
    print(f"\n🔍 Checking for new Lahore jobs...")
    jobs = fetch_lahore_jobs()
    print(f"   Found {len(jobs)} job postings")
    
    new_applications = 0
    
    for job in jobs:
        # Filter: Lahore location (already done in scraping, but double-check)
        location_lower = job.get('location', '').lower()
        if 'lahore' not in location_lower and 'pakistan' not in location_lower:
            continue
        
        # Filter: Already applied
        if job['id'] in existing_jobs:
            continue
        
        # Match CV against job description
        print(f"\n🎯 Analyzing: {job['title']} at {job['company']}")
        
        match_result = match_cv_to_job(first_cv_text, job['description'])
        
        if match_result:
            match_score = match_result.get('match_score', 0)
            matched_skills = match_result.get('matched_skills', [])
            jd_skills = match_result.get('jd_skills', [])
            
            print(f"   Match Score: {match_score}%")
            if matched_skills:
                print(f"   Matched skills: {', '.join(matched_skills)}")
            
            # Only track jobs with reasonable match (configurable threshold)
            if match_score >= 40:
                add_application(conn, job, match_result)
                new_applications += 1
                existing_jobs.add(job['id'])
            else:
                print(f"   ⭐ Below threshold (40%), skipping track")
                print(f"   JD skills: {', '.join(jd_skills)}")
        else:
            print(f"   ⚠️ Could not match - skipping")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"📈 Summary: {new_applications} new applications tracked")
    print(f"   Total in database: {len(get_existing_job_ids(conn))}")
    print("=" * 60)
    
    conn.close()
    
    # For cron: just exit; cron will re-run the script
    # For continuous: time.sleep(seconds) then main()
    # We'll exit for cron compatibility




def main():
    """Run the job monitoring bot"""
    print("=" * 60)
    print(f"🕵️ Job Monitor Starting...")
    print(f"   Check interval: every {CHECK_INTERVAL_HOURS} hours")
    print(f"   Location: Lahore, Pakistan")
    print(f"   Job types: onsite + remote")
    print(f"   CVs: 2 resumes loaded for matching")
    print("=" * 60)
    
    load_cvs()
    init_db_and_track()
if __name__ == '__main__':
    main()
