import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import os

load_dotenv()

cred_path = "serviceAccountKey.json"
if not firebase_admin._apps:
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
    else:
        cred = None
    firebase_admin.initialize_app(cred, {
        'databaseURL': os.getenv('RTDB_URL', 'https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/')
    })

db = firestore.client()
