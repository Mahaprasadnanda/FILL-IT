import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import os

load_dotenv()

RTDB_URL = os.getenv('RTDB_URL')
if not RTDB_URL:
    raise RuntimeError("RTDB_URL environment variable is required")

cred_path = "serviceAccountKey.json"
if not firebase_admin._apps:
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
    else:
        cred = credentials.ApplicationDefault()
        
    firebase_admin.initialize_app(cred, {
        'databaseURL': RTDB_URL
    })

db = firestore.client()
