# main.py
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from login import router as login_router
from signup import router as signup_router
from c_book import router as book_router
from c_triphistory import router as trip_history_router
from d_book import router as driver_router
from regret_scheduler import scheduler
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exceptions import RequestValidationError
import requests
from services import services_router
import os


app = FastAPI()

SESSION_SECRET_KEY = os.getenv('SESSION_SECRET_KEY', 'default-insecure-secret-key')

# Session middleware - add this before CORS
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,  # Loaded from environment variable
    session_cookie="session"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://fillitcloudnexus.web.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from the current directory
app.mount("/static", StaticFiles(directory="."), name="static")

# Mount routers
app.include_router(login_router)
app.include_router(signup_router)
app.include_router(book_router)
app.include_router(trip_history_router)
app.include_router(driver_router)
app.include_router(services_router, prefix='/api')

RESEND_API_KEY = os.getenv('RESEND_API_KEY')
RESEND_API_URL = 'https://api.resend.com/emails'

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={"Access-Control-Allow-Origin": " https://fillitcloudnexus.web.app"}
    )

@app.post('/api/contact')
async def contact(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    source: str = Form(...),
    other_source: str = Form(None),
    message: str = Form(...)
):
    try:
        body = f"""Name: {name}\nEmail: {email}\nPhone: {phone}\nSource: {source}\nOther Source: {other_source or ''}\nMessage: {message}"""
        data = {
            'from': 'FILLit <onboarding@resend.dev>',
            'to': 'mail2mahaprasad45@gmail.com',
            'subject': 'New Contact Form Submission',
            'text': body
        }
        headers = {
            'Authorization': f'Bearer {RESEND_API_KEY}',
            'Content-Type': 'application/json'
        }
        print("Sending email with data:", data)  # Debug log
        response = requests.post(RESEND_API_URL, json=data, headers=headers)
        print("Resend API response:", response.status_code, response.text)  # Debug log
        
        if response.status_code == 200:
            return {'status': 'success'}
        else:
            error_detail = response.text
            print(f"Error sending email: {error_detail}")  # Debug log
            return {'status': 'error', 'detail': error_detail}
    except Exception as e:
        print(f"Exception in contact endpoint: {str(e)}")  # Debug log
        return {'status': 'error', 'detail': str(e)}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
