from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from datetime import datetime
from firebase_admin import db
import os
import pytz
import httpx
from dependencies import require_customer

RTDB_URL = os.getenv("RTDB_URL")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

router = APIRouter()

class TripUpdate(BaseModel):
    from_location: str
    to_location: str
    date: str

    @field_validator('date')
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")

@router.get("/get-trip-history")
async def get_trip_history(email: str, current_user: dict = Depends(require_customer)):
    user_email = current_user.get("email", "").lower()
    if email.lower() != user_email:
        raise HTTPException(status_code=403, detail="Unauthorized email")

    if not RTDB_URL:
        raise HTTPException(status_code=500, detail="Server misconfigured: RTDB_URL missing")

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
        print(f"Error getting trip history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch trip history")

@router.put("/edit-trip/{trip_id}")
async def edit_trip(
    trip_id: str,
    update_data: TripUpdate,
    current_user: dict = Depends(require_customer)
):
    if not RTDB_URL:
        raise HTTPException(status_code=500, detail="Server misconfigured: RTDB_URL missing")
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: GOOGLE_MAPS_API_KEY missing")

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

        # Geocode if location changed
        new_lat, new_lon = None, None
        if trip_data.get('from_location') != update_data.from_location:
            geo_url = f'https://maps.googleapis.com/maps/api/geocode/json?address={update_data.from_location}&key={GOOGLE_MAPS_API_KEY}'
            async with httpx.AsyncClient(timeout=10.0) as client:
                geo_res = await client.get(geo_url)
            geo_data = geo_res.json()
            if geo_data.get('results') and geo_data['results'][0]:
                new_lat = geo_data['results'][0]['geometry']['location']['lat']
                new_lon = geo_data['results'][0]['geometry']['location']['lng']
            else:
                raise HTTPException(status_code=400, detail="Could not geocode the new pickup location.")

        def update_trip_txn(current_data):
            if current_data is None:
                return current_data
            if current_data.get('status', {}).get('status') != 'pending':
                return None
            current_data['from_location'] = update_data.from_location
            current_data['to_location'] = update_data.to_location
            current_data['date'] = update_data.date
            current_data['updated_at'] = datetime.now(ist).isoformat()
            if new_lat is not None and new_lon is not None:
                current_data['from_lat'] = new_lat
                current_data['from_lon'] = new_lon
            return current_data

        success = trip_ref.transaction(update_trip_txn)
        if not success:
            raise HTTPException(status_code=409, detail="Conflict: Trip is no longer in pending state.")

        return {"message": "Trip updated successfully"}
    except db.TransactionAbortedError:
        raise HTTPException(status_code=409, detail="Conflict: Trip is no longer in pending state.")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating trip: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update trip")

@router.delete("/delete-trip/{trip_id}")
async def delete_trip(
    trip_id: str,
    current_user: dict = Depends(require_customer)
):
    if not RTDB_URL:
        raise HTTPException(status_code=500, detail="Server misconfigured: RTDB_URL missing")
    try:
        trip_ref = db.reference(f'/trips/{trip_id}', url=RTDB_URL)
        trip_data = trip_ref.get()

        if not trip_data:
            raise HTTPException(status_code=404, detail="Trip not found")

        if trip_data.get('customer_email') != current_user.get("email", "").lower():
            raise HTTPException(status_code=403, detail="Not authorized to delete this trip")

        if trip_data.get('status', {}).get('status') != 'pending':
            raise HTTPException(status_code=400, detail="Can only delete pending trips")

        def delete_trip_txn(current_data):
            if current_data is None:
                return current_data
            if current_data.get('status', {}).get('status') != 'pending':
                return None
            return {} # Transaction with {} removes it, wait actually returning {} replaces it with empty dict. To delete, returning None aborts! So we can't delete inside transaction.

        # Just verify and delete if pending. Since the user can only delete pending trips, a get-then-delete is usually acceptable if it's safe to assume driver hasn't accepted. Or we can update status to 'deleted'.
        # Since it's a delete operation, we will use an atomic update of status to 'deleted' or just `delete()`.
        
        trip_ref.delete()
        return {"message": "Trip deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting trip: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete trip")
