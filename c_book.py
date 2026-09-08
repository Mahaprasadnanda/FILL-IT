from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
import os
import httpx
from firebase_admin import db
from datetime import datetime
import pytz
from dependencies import require_customer

router = APIRouter()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
RTDB_URL = os.getenv("RTDB_URL", "https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/")

class TripBookingRequest(BaseModel):
    email: EmailStr
    from_location: str
    to_location: str
    date: str  

@router.post('/book-trip')
async def book_trip(request: TripBookingRequest, current_user: dict = Depends(require_customer)):
    user_email = current_user.get("email", "").lower()
    if request.email.lower() != user_email:
        raise HTTPException(status_code=403, detail="Cannot book trip for another user.")

    try:
        from_lat, from_lon = None, None
        if GOOGLE_MAPS_API_KEY:
            geo_url = f'https://maps.googleapis.com/maps/api/geocode/json?address={request.from_location}&key={GOOGLE_MAPS_API_KEY}'
            async with httpx.AsyncClient() as client:
                geo_res = await client.get(geo_url)
            geo_data = geo_res.json()
            if geo_data.get('results') and geo_data['results'][0]:
                from_lat = geo_data['results'][0]['geometry']['location']['lat']
                from_lon = geo_data['results'][0]['geometry']['location']['lng']
            else:
                raise HTTPException(status_code=400, detail="Could not geocode the pickup location.")
        else:
            raise HTTPException(status_code=500, detail="Google Maps API key not configured.")

        ist = pytz.timezone('Asia/Kolkata')
        customer_phone = current_user.get('customer_data', {}).get('phone', '')

        booking_data = {
            "customer_email": user_email,
            "customer_phone": customer_phone,
            "from_location": request.from_location,
            "to_location": request.to_location,
            "from_lat": from_lat,
            "from_lon": from_lon,
            "date": request.date,
            "created_at": datetime.now(ist).isoformat(),
            "status": {
                "status": "pending"
            }
        }
        
        trips_ref = db.reference('/trips', url=RTDB_URL)
        new_trip_ref = trips_ref.push(booking_data)
        return {
            "message": "Trip booked successfully!",
            "booking_id": new_trip_ref.key,
            "data": booking_data
        }
    except HTTPException:
        raise
    except Exception as e:
        print('Error in /book-trip:', str(e))
        raise HTTPException(status_code=500, detail="Failed to book trip due to an internal error.") 
