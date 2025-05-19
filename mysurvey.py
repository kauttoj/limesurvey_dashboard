import os
from dotenv import load_dotenv

load_dotenv()

# --- Survey-specific configuration ---
API_URL = os.getenv('LIMESURVEY_URL')
USERNAME = os.getenv('LIMESURVEY_USERNAME')
PASSWORD = os.getenv('LIMESURVEY_PASSWORD')
SURVEY_ID = int(os.getenv('LIMESURVEY_SURVEY_ID', 0))
LASTPAGE_THRESHOLD = int(os.getenv('LIMESURVEY_LASTPAGE', 0))

# Mapping of question codes to display labels
PARAMETERS = {
    'lastpage': 'Last Page Reached',
    'is_completed': 'Completed Survey',
    'q1age': 'Age',
    'q1gender': 'Gender',
    'q3edu': 'Education Level',
    'q4lang': 'Language Skill',
    'q5reading': 'Reading Skill',
    'q6onlinenews': 'Online News Capacity',
    'q7readfreq': 'Frequency of Reading',
}
