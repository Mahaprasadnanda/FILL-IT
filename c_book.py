from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
import firebase_admin
from firebase_admin import db
from datetime import datetime
import pytz

router = APIRouter()

class TripBookingRequest(BaseModel):
    email: EmailStr
    from_location: str
    to_location: str
    date: str  # ISO format (YYYY-MM-DD)

@router.post('/book-trip')
async def book_trip(request: TripBookingRequest):
    try:
        ist = pytz.timezone('Asia/Kolkata')
        booking_data = {
            "customer_email": request.email.lower(),
            "from_location": request.from_location,
            "to_location": request.to_location,
            "date": request.date,
            "created_at": datetime.now(ist).isoformat(),
            "status": {
                "status": "pending"
            }
        }
        # Add to Realtime Database with auto-generated key
        trips_ref = db.reference('/trips', url='https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/')
        new_trip_ref = trips_ref.push(booking_data)
        return {
            "message": "Trip booked successfully!",
            "booking_id": new_trip_ref.key,
            "data": booking_data
        }
    except Exception as e:
        print('Error in /book-trip:', str(e))
        raise HTTPException(status_code=500, detail=f"Failed to book trip: {str(e)}") 