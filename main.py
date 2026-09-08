from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from login import router as login_router
from signup import router as signup_router
from c_book import router as book_router
from c_triphistory import router as trip_history_router
from d_book import router as driver_router
from regret_scheduler import scheduler
import httpx
import os

SESSION_SECRET_KEY = os.getenv('SESSION_SECRET_KEY')
if not SESSION_SECRET_KEY:
    raise RuntimeError("SESSION_SECRET_KEY environment variable is required")

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,  
    session_cookie="session",
    https_only=True,
    same_site="lax"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://fillitcloudnexus.web.app", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="."), name="static")

app.include_router(login_router)
app.include_router(signup_router)
app.include_router(book_router)
app.include_router(trip_history_router)
app.include_router(driver_router)

RESEND_API_KEY = os.getenv('RESEND_API_KEY')
RESEND_API_URL = 'https://api.resend.com/emails'

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled server error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."}
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
    if not RESEND_API_KEY:
        raise HTTPException(status_code=500, detail="Resend API key not configured.")
        
    try:
        body = f"Name: {name}\nEmail: {email}\nPhone: {phone}\nSource: {source}\nOther Source: {other_source or ''}\nMessage: {message}"
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
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(RESEND_API_URL, json=data, headers=headers)
        
        if response.status_code == 200:
            return {'status': 'success'}
        else:
            print(f"Error sending email: {response.text}")  
            return {'status': 'error', 'detail': "Failed to send email"}
    except Exception as e:
        print(f"Exception in contact endpoint: {str(e)}")  
        raise HTTPException(status_code=500, detail="Failed to process contact form")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
