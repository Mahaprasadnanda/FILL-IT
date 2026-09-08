from fastapi import APIRouter, HTTPException, Query, Header, Body, Request, Depends
from pydantic import BaseModel, EmailStr
import httpx
from firebase_config import db
import os
from firebase_admin import auth
from dependencies import get_current_user

router = APIRouter()

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class UpdateProfileRequest(BaseModel):
    email: EmailStr
    phone: str

class LogoutRequest(BaseModel):
    id_token: str

@router.post("/login")
async def login(user: LoginRequest, request: Request):
    if not FIREBASE_API_KEY:
        raise HTTPException(status_code=500, detail="Server configuration error.")
    login_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {
        "email": user.email.lower(),
        "password": user.password,
        "returnSecureToken": True
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(login_url, json=payload)
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    data = response.json()
    id_token = data.get("idToken")

    verify_url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_API_KEY}"
    async with httpx.AsyncClient() as client:
        verify_res = await client.post(verify_url, json={"idToken": id_token})
    if verify_res.status_code != 200:
        raise HTTPException(status_code=401, detail="Failed to verify email.")

    user_info = verify_res.json().get("users", [])
    if not user_info or not user_info[0].get("emailVerified", False):
        raise HTTPException(status_code=403, detail="Email not verified.")

    email = user.email.lower()
    customer_doc = db.collection("Customer").document(email).get()
    driver_doc = db.collection("Driver").document(email).get()
    
    if customer_doc.exists:
        role = "customer"
    elif driver_doc.exists:
        role = "driver"
    else:
        raise HTTPException(status_code=404, detail="User role not found in Firestore.")

    request.session["user_id"] = email
    request.session["role"] = role
    request.session["email"] = email
    
    if role == "driver":
        request.session["driver_id"] = email

    return {
        "idToken": id_token,
        "email": email,
        "role": role,
        "refreshToken": data.get("refreshToken")
    }

@router.post("/refresh-token")
async def refresh_token(request: RefreshTokenRequest):
    if not FIREBASE_API_KEY:
        raise HTTPException(status_code=500, detail="Server configuration error.")
    refresh_url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": request.refresh_token
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(refresh_url, data=payload)
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Failed to refresh token.")

    data = response.json()
    return {
        "idToken": data.get("id_token"),
        "refreshToken": data.get("refresh_token")
    }

@router.get("/get-role")
def get_role(
    email: str = Query(..., description="User email to fetch role"),
    current_user: dict = Depends(get_current_user)
):
    email = email.lower()
    if current_user.get("email", "").lower() != email:
        raise HTTPException(status_code=403, detail="Unauthorized email")
        
    if db.collection("Customer").document(email).get().exists:
        return {"role": "customer"}
    elif db.collection("Driver").document(email).get().exists:
        return {"role": "driver"}
    raise HTTPException(status_code=404, detail="User not found in any role.")

@router.get("/get-profile")
def get_profile(
    email: str = Query(..., description="Email to fetch user profile"),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("email", "").lower() != email.lower():
        raise HTTPException(status_code=403, detail="Unauthorized email")

    customer_ref = db.collection("Customer").document(email.lower()).get()
    if customer_ref.exists:
        return customer_ref.to_dict()

    driver_ref = db.collection("Driver").document(email.lower()).get()
    if driver_ref.exists:
        return driver_ref.to_dict()

    raise HTTPException(status_code=404, detail="User not found in Customer or Driver collections")

@router.post("/update-profile")
async def update_profile(
    request: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("email", "").lower() != request.email.lower():
        raise HTTPException(status_code=403, detail="Unauthorized email")

    customer_ref = db.collection("Customer").document(request.email.lower())
    if not customer_ref.get().exists:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer_ref.update({"phone": request.phone})
    return {"message": "Profile updated successfully"}

@router.post("/logout")
async def logout(
    request_body: LogoutRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    try:
        uid = current_user.get("uid")
        auth.revoke_refresh_tokens(uid)
        request.session.clear()
        return {"message": "Successfully logged out"}
    except Exception as e:
        print(f"Logout failed for UID {uid}: {str(e)}")
        raise HTTPException(status_code=500, detail="Logout failed.")
