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
    'token': 'token',
    'startdate':'startdate',
    'lastpage': 'Viimeisin tallennettu sivu',
    'is_completed': 'Vastattu loppuun',
    'q1age': 'Mikä on ikäsi?',
    'q1gender': 'Mikä on sukupuolesi?',
    'q3edu': 'Mikä on korkein suorittamasi koulutus?',
    'q4lang': 'Mikä on suomen kielen tasosi?',
    'q5reading': 'Millainen on lukutaitosi suomen kielellä?',
    'q6onlinenews': 'Miten hyvin pystyt lukemaan suomeksi uutisia mediasta, esimerkiksi Helsingin Sanomat tai YLEn verkkosivut?',
    'q7readfreq': 'Kuinka usein luet suomenkielisiä uutisia?',
}
