from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import auth
from firebase_config import db

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

def require_customer(user: dict = Depends(get_current_user)):
    email = user.get('email', '').lower()
    customer_ref = db.collection('Customer').document(email).get()
    if not customer_ref.exists:
        raise HTTPException(status_code=403, detail='Access denied. Customer role required.')
    user['customer_data'] = customer_ref.to_dict()
    return user

def require_driver(user: dict = Depends(get_current_user)):
    email = user.get('email', '').lower()
    driver_ref = db.collection('Driver').document(email).get()
    if not driver_ref.exists:
        raise HTTPException(status_code=403, detail='Access denied. Driver role required.')
    user['driver_data'] = driver_ref.to_dict()
    return user
