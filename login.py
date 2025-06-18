from fastapi import APIRouter, HTTPException, Query, Header, Body, Request
from pydantic import BaseModel, EmailStr
import requests
from firebase_config import db
import os
from firebase_admin import auth

router = APIRouter()

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
if not FIREBASE_API_KEY:
    raise RuntimeError("FIREBASE_API_KEY is not set in environment variables.")

# Pydantic model for login request
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# Pydantic model for refresh token request
class RefreshTokenRequest(BaseModel):
    refresh_token: str

# Pydantic model for update profile request
class UpdateProfileRequest(BaseModel):
    email: EmailStr
    phone: str

# Pydantic model for logout request
class LogoutRequest(BaseModel):
    id_token: str

# Login route
@router.post("/login")
async def login(user: LoginRequest, request: Request):
    login_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {
        "email": user.email.lower(),
        "password": user.password,
        "returnSecureToken": True
    }
    response = requests.post(login_url, json=payload)
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    data = response.json()
    id_token = data.get("idToken")

    # Verify email is confirmed
    verify_url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_API_KEY}"
    verify_res = requests.post(verify_url, json={"idToken": id_token})
    if verify_res.status_code != 200:
        raise HTTPException(status_code=401, detail="Failed to verify email.")

    user_info = verify_res.json().get("users", [])
    if not user_info or not user_info[0].get("emailVerified", False):
        raise HTTPException(status_code=403, detail="Email not verified.")

    email = user.email.lower()

    # Get role and user ID from Firestore
    customer_doc = db.collection("Customer").document(email).get()
    driver_doc = db.collection("Driver").document(email).get()
    
    if customer_doc.exists:
        role = "customer"
        user_id = email
    elif driver_doc.exists:
        role = "driver"
        user_id = email
    else:
        raise HTTPException(status_code=404, detail="User role not found in Firestore.")

    # Set session data
    request.session["user_id"] = user_id
    request.session["role"] = role
    request.session["email"] = email
    
    if role == "driver":
        request.session["driver_id"] = email  # Set driver_id for driver routes

    return {
        "idToken": id_token,
        "email": email,
        "role": role,
        "refreshToken": data.get("refreshToken")
    }

# Refresh token route
@router.post("/refresh-token")
def refresh_token(request: RefreshTokenRequest):
    refresh_url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": request.refresh_token
    }
    response = requests.post(refresh_url, data=payload)
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Failed to refresh token.")

    data = response.json()
    return {
        "idToken": data.get("id_token"),
        "refreshToken": data.get("refresh_token")
    }

# Role query endpoint
@router.get("/get-role")
def get_role(email: str = Query(..., description="User email to fetch role")):
    email = email.lower()
    if db.collection("Customer").document(email).get().exists:
        return {"role": "customer"}
    elif db.collection("Driver").document(email).get().exists:
        return {"role": "driver"}
    raise HTTPException(status_code=404, detail="User not found in any role.")

# Profile query endpoint
@router.get("/get-profile")
def get_profile(
    email: str = Query(..., description="Email to fetch user profile"),
    authorization: str = Header(None)
):
    print(f"Fetching profile for email: {email}")

    if not authorization or not authorization.startswith("Bearer "):
        print(f"Missing or invalid Authorization header: {authorization}")
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")

    id_token = authorization.replace("Bearer ", "").strip()

    try:
        # Uncomment this block for production
        # decoded_token = auth.verify_id_token(id_token)
        # if decoded_token.get("email").lower() != email.lower():
        #     raise HTTPException(status_code=403, detail="Unauthorized email")

        customer_ref = db.collection("Customer").document(email.lower()).get()
        if customer_ref.exists:
            return customer_ref.to_dict()

        driver_ref = db.collection("Driver").document(email.lower()).get()
        if driver_ref.exists:
            return driver_ref.to_dict()

        raise HTTPException(status_code=404, detail="User not found in Customer or Driver collections")

    except Exception as e:
        print(f"Error in get-profile: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

# Update profile endpoint
@router.post("/update-profile")
async def update_profile(
    request: UpdateProfileRequest,
    authorization: str = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")

    id_token = authorization.replace("Bearer ", "").strip()

    try:
        # Verify the token
        decoded_token = auth.verify_id_token(id_token)
        if decoded_token.get("email").lower() != request.email.lower():
            raise HTTPException(status_code=403, detail="Unauthorized email")

        # Update the phone number in Firestore
        customer_ref = db.collection("Customer").document(request.email.lower())
        if not customer_ref.get().exists:
            raise HTTPException(status_code=404, detail="Customer not found")

        customer_ref.update({"phone": request.phone})
        return {"message": "Profile updated successfully"}

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Update failed: {str(e)}")

# Logout endpoint
@router.post("/logout")
async def logout(request: LogoutRequest):
    try:
        # Verify the ID token to get the user's UID
        decoded_token = auth.verify_id_token(request.id_token)
        uid = decoded_token.get("uid")
        
        # Revoke refresh tokens for the user
        auth.revoke_refresh_tokens(uid)
        
        return {"message": "Successfully logged out"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Logout failed: {str(e)}")