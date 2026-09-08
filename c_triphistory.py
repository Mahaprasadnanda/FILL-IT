from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from firebase_admin import db
import os
import pytz
from dependencies import require_customer

RTDB_URL = os.getenv("RTDB_URL", "https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/")

router = APIRouter()

class TripUpdate(BaseModel):
    from_location: str
    to_location: str
    date: str

@router.get("/get-trip-history")
async def get_trip_history(email: str, current_user: dict = Depends(require_customer)):
    user_email = current_user.get("email", "").lower()
    if email.lower() != user_email:
        raise HTTPException(status_code=403, detail="Unauthorized email")

    try:
        trips_ref = db.reference('/trips', url=RTDB_URL)
        customer_trips = trips_ref.order_by_child('customer_email').equal_to(user_email).get()
        
        if not customer_trips:
            return {"trips": []}

        customer_trips_dict = dict(customer_trips)
        formatted_trips = []
        for trip_id, trip_data in customer_trips_dict.items():
            date_str = trip_data.get('date')
            try:
                if '-' in str(date_str):
                    booking_date = datetime.strptime(date_str, '%Y-%m-%d')
                else:
                    booking_date = datetime.strptime(date_str, '%d/%m/%Y')
            except Exception:
                booking_date = None

            current_date = datetime.now()
            status_val = trip_data.get('status', {}).get('status', 'pending')
            
            if booking_date and booking_date < current_date and status_val == 'pending':
                trip_ref = db.reference(f'/trips/{trip_id}', url=RTDB_URL)
                trip_ref.child('status').update({
                    'status': 'regret',
                    'updated_at': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat()
                })
                trip_data['status'] = {'status': 'regret'}

            formatted_trips.append({
                "booking_id": trip_id,
                "customer_email": trip_data.get('customer_email'),
                "from_location": trip_data.get('from_location'),
                "to_location": trip_data.get('to_location'),
                "date": trip_data.get('date'),
                "created_at": trip_data.get('created_at'),
                "updated_at": trip_data.get('updated_at'),
                "status": trip_data.get('status', {})
            })

        return {"trips": formatted_trips}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch trip history")

@router.put("/edit-trip/{trip_id}")
async def edit_trip(
    trip_id: str,
    update_data: TripUpdate,
    current_user: dict = Depends(require_customer)
):
    try:
        ist = pytz.timezone('Asia/Kolkata')
        trip_ref = db.reference(f'/trips/{trip_id}', url=RTDB_URL)
        trip_data = trip_ref.get()

        if not trip_data:
            raise HTTPException(status_code=404, detail="Trip not found")

        if trip_data.get('customer_email') != current_user.get("email", "").lower():
            raise HTTPException(status_code=403, detail="Not authorized to edit this trip")

        if trip_data.get('status', {}).get('status') != 'pending':
            raise HTTPException(status_code=400, detail="Can only edit pending trips")

        trip_ref.update({
            "from_location": update_data.from_location,
            "to_location": update_data.to_location,
            "date": update_data.date,
            "updated_at": datetime.now(ist).isoformat()
        })

        return {"message": "Trip updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update trip")

@router.delete("/delete-trip/{trip_id}")
async def delete_trip(
    trip_id: str,
    current_user: dict = Depends(require_customer)
):
    try:
        trip_ref = db.reference(f'/trips/{trip_id}', url=RTDB_URL)
        trip_data = trip_ref.get()

        if not trip_data:
            raise HTTPException(status_code=404, detail="Trip not found")

        if trip_data.get('customer_email') != current_user.get("email", "").lower():
            raise HTTPException(status_code=403, detail="Not authorized to delete this trip")

        if trip_data.get('status', {}).get('status') != 'pending':
            raise HTTPException(status_code=400, detail="Can only delete pending trips")

        trip_ref.delete()
        return {"message": "Trip deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete trip")
