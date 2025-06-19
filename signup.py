
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import os
import requests
from firebase_config import db
from datetime import datetime
from firebase_admin import auth
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")

class SignupRequest(BaseModel):
    name: str
    email: str
    phone: str
    password: str
    role: str
    vehicle_number: Optional[str] = None
    vehicle_chassis: Optional[str] = None

class UpdatePhoneRequest(BaseModel):
    email: str
    phone: str

@router.post("/signup")
def signup(user: SignupRequest):
    email = user.email.lower()  
    if not email:
        raise HTTPException(status_code=400, detail="Email is required and must be a string.")
    signup_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {
        "email": email,
        "password": user.password,
        "returnSecureToken": True
    }

    res = requests.post(signup_url, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.json())

    id_token = res.json()["idToken"]

    
    verify_url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_API_KEY}"
    verify_res = requests.post(verify_url, json={"requestType": "VERIFY_EMAIL", "idToken": id_token})
    if verify_res.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to send verification email")

    
    collection = "Customer" if user.role.lower() == "customer" else "Driver"
    data = {
        "name": user.name,
        "email": email,
        "phone": user.phone,
        "role": user.role.lower(),
        "created_at": datetime.utcnow()
    }
    if user.role.lower() == "driver":
        if user.vehicle_number is not None:
            data["vehicle_number"] = user.vehicle_number
        if user.vehicle_chassis is not None:
            data["vehicle_chassis"] = user.vehicle_chassis
    db.collection(collection).document(str(email)).set(data)

    return {"message": "User created. Verification email sent."}

@router.post("/verify-phone-token")
async def verify_phone_token(request: Request):
    body = await request.json()
    id_token = body.get("idToken")
    if not id_token:
        raise HTTPException(status_code=400, detail="Missing ID token")

    try:
        decoded_token = auth.verify_id_token(id_token)
        phone_number = decoded_token.get("phone_number")
        uid = decoded_token.get("uid")
        return {"message": "Phone number verified", "uid": uid, "phone_number": phone_number}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/update-phone")
def update_phone(user: UpdatePhoneRequest, authorization: str = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")
    
    id_token = authorization.split("Bearer ")[1]
    try:
        decoded_token = auth.verify_id_token(id_token)
        if decoded_token.get("email").lower() != user.email.lower():
            raise HTTPException(status_code=403, detail="Unauthorized email")
        
        db.collection("Customer").document(user.email.lower()).update({
            "phone": user.phone
        })
        return {"message": "Phone number updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Failed to update phone: {str(e)}")
