from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db
import os
from dotenv import load_dotenv
import json
import pytz

load_dotenv()

# Get the existing Firebase app
app = firebase_admin.get_app()

# Get database reference with URL
db_ref = db.reference('/', url='https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/')

router = APIRouter()

# Pydantic models
class TripStatus(BaseModel):
    status: str  # "pending", "driver_assigned", "trip_completed"
    driver_email: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    vehicle_number: Optional[str] = None
    assigned_at: Optional[str] = None
    completed_at: Optional[str] = None

class TripHistory(BaseModel):
    booking_id: str
    customer_email: EmailStr
    from_location: str
    to_location: str
    date: str
    created_at: str
    status: TripStatus

class TripUpdate(BaseModel):
    from_location: str
    to_location: str
    date: str

# Get trip history for a customer
@router.get("/get-trip-history")
async def get_trip_history(
    email: str,
    authorization: str = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")

    try:
        # Get reference to the trips node
        trips_ref = db.reference('/trips', url='https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/')
        
        # Query trips for the specific customer
        customer_trips = trips_ref.order_by_child('customer_email').equal_to(email).get()
        
        if not customer_trips:
            return {"trips": []}

        # Cast customer_trips to a dict to avoid linter errors
        customer_trips_dict = dict(customer_trips)
        # Format the response
        formatted_trips = []
        for trip_id, trip_data in customer_trips_dict.items():
            date_str = trip_data.get('date')
            try:
                booking_date = datetime.strptime(date_str, '%d/%m/%Y') if date_str else None
            except Exception as e:
                print(f"Invalid date format for trip {trip_id}: {date_str} ({e})")
                booking_date = None

            current_date = datetime.now()
            status_val = trip_data.get('status', {}).get('status', 'pending')
            if booking_date and booking_date < current_date and status_val == 'pending':
                # Update the trip status to 'regret' in the database
                trip_ref = db.reference(f'/trips/{trip_id}', url='https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/')
                trip_ref.child('status').update({
                    'status': 'regret',
                    'updated_at': str(datetime.now(pytz.timezone('Asia/Kolkata')).isoformat())
                })
                # Update the status in the response
                trip_data['status'] = {'status': 'regret'}
            formatted_trips.append({
                "booking_id": trip_id,
                "customer_email": trip_data.get('customer_email'),
                "from_location": trip_data.get('from_location'),
                "to_location": trip_data.get('to_location'),
                "date": trip_data.get('date'),
                "created_at": trip_data.get('created_at'),
                "updated_at": trip_data.get('updated_at'),
                "status": {
                    "status": trip_data.get('status', {}).get('status', 'pending'),
                    "driver_email": trip_data.get('status', {}).get('driver_email'),
                    "driver_name": trip_data.get('status', {}).get('driver_name'),
                    "driver_phone": trip_data.get('status', {}).get('driver_phone'),
                    "vehicle_number": trip_data.get('status', {}).get('vehicle_number'),
                    "assigned_at": trip_data.get('status', {}).get('assigned_at'),
                    "completed_at": trip_data.get('status', {}).get('completed_at')
                }
            })

        return {"trips": formatted_trips}

    except Exception as e:
        print('Error in /get-trip-history:', str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch trip history: {str(e)}")

# Update trip status (for drivers)
@router.post("/update-trip-status")
async def update_trip_status(
    booking_id: str,
    status: str,
    driver_email: Optional[str] = None,
    driver_name: Optional[str] = None,
    driver_phone: Optional[str] = None,
    vehicle_number: Optional[str] = None,
    authorization: str = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")

    try:
        ist = pytz.timezone('Asia/Kolkata')
        # Get reference to the specific trip
        trip_ref = db.reference(f'/trips/{booking_id}', url='https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/')
        trip_data = trip_ref.get()

        if not trip_data:
            raise HTTPException(status_code=404, detail="Trip not found")

        # Cast trip_data to a dict to avoid linter errors
        trip_data_dict = dict(trip_data)
        # Update status
        status_update = {
            "status": status,
            "updated_at": datetime.now(ist).isoformat()
        }

        if status == "driver_assigned":
            if not all([driver_email, driver_name, driver_phone, vehicle_number]):
                raise HTTPException(status_code=400, detail="Driver details required for assignment")
            
            status_update.update({
                "driver_email": driver_email,
                "driver_name": driver_name,
                "driver_phone": driver_phone,
                "vehicle_number": vehicle_number,
                "assigned_at": datetime.now(ist).isoformat()
            })
        elif status == "trip_completed":
            status_update["completed_at"] = datetime.now(ist).isoformat()

        # Convert status_update to a list of tuples for the update method
        status_update_list = [(k, v) for k, v in status_update.items()]
        trip_ref.update(status_update_list)
        return {"message": "Trip status updated successfully"}

    except Exception as e:
        print('Error in /update-trip-status:', str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update trip status: {str(e)}")

# Find nearby trips (for drivers)
@router.get("/find-nearby-trips")
async def find_nearby_trips(
    from_location: str,
    date: str,
    authorization: str = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")

    try:
        # Get reference to the trips node
        trips_ref = db.reference('/trips')
        
        # Query trips for the specific date and pending status
        trips = trips_ref.order_by_child('date').equal_to(date).get()
        
        if not trips:
            return {"trips": []}

        # Cast trips to a dict to avoid linter errors
        trips_dict = dict(trips)
        # Filter trips by status and location (you'll need to implement the 10km radius check here)
        nearby_trips = []
        for trip_id, trip_data in trips_dict.items():
            if trip_data.get('status', {}).get('status') == 'pending':
                # Add location-based filtering here
                nearby_trips.append({
                    "booking_id": trip_id,
                    "customer_email": trip_data.get('customer_email'),
                    "from_location": trip_data.get('from_location'),
                    "to_location": trip_data.get('to_location'),
                    "date": trip_data.get('date'),
                    "created_at": trip_data.get('created_at')
                })

        return {"trips": nearby_trips}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to find nearby trips: {str(e)}")

# Edit trip
@router.put("/edit-trip/{trip_id}")
async def edit_trip(
    trip_id: str,
    update_data: TripUpdate,
    authorization: str = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")

    try:
        ist = pytz.timezone('Asia/Kolkata')
        # Get reference to the specific trip
        trip_ref = db.reference(f'/trips/{trip_id}', url='https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/')
        trip_data = trip_ref.get()

        if not trip_data:
            raise HTTPException(status_code=404, detail="Trip not found")

        # Only allow editing if trip is pending
        if trip_data.get('status', {}).get('status') != 'pending':
            raise HTTPException(status_code=400, detail="Can only edit pending trips")

        # Update the trip with updated_at timestamp
        trip_ref.update({
            "from_location": update_data.from_location,
            "to_location": update_data.to_location,
            "date": update_data.date,
            "updated_at": datetime.now(ist).isoformat()
        })

        return {"message": "Trip updated successfully"}
    except Exception as e:
        print('Error in /edit-trip:', str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update trip: {str(e)}")

# Delete trip
@router.delete("/delete-trip/{trip_id}")
async def delete_trip(
    trip_id: str,
    authorization: str = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")

    try:
        # Get reference to the specific trip
        trip_ref = db.reference(f'/trips/{trip_id}', url='https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/')
        trip_data = trip_ref.get()

        if not trip_data:
            raise HTTPException(status_code=404, detail="Trip not found")

        # Only allow deletion if trip is pending
        if trip_data.get('status', {}).get('status') != 'pending':
            raise HTTPException(status_code=400, detail="Can only delete pending trips")

        # Delete the trip
        trip_ref.delete()

        return {"message": "Trip deleted successfully"}
    except Exception as e:
        print('Error in /delete-trip:', str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete trip: {str(e)}") 