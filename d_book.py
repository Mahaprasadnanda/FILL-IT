from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import httpx
from datetime import datetime, timezone
import math
from firebase_admin import db as rtdb
import os
import pytz
from dependencies import require_driver

router = APIRouter()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
RTDB_URL = os.getenv("RTDB_URL")

class TripActionRequest(BaseModel):
    trip_id: str

class SearchTripsRequest(BaseModel):
    from_location: str

class UpdatePhoneRequest(BaseModel):
    phone: str

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

@router.get("/d_home", response_class=HTMLResponse)
async def d_home(request: Request):
    try:
        with open("d_home.html", "r") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Driver Home</h1>")

@router.get("/api/driver/profile")
async def get_driver_profile(current_user: dict = Depends(require_driver)):
    driver_data = current_user.get("driver_data", {})
    return {
        "name": driver_data.get("name", ""),
        "email": driver_data.get("email", ""),
        "phone": driver_data.get("phone", "")
    }

@router.post("/api/driver/update_phone")
async def update_phone(request: UpdatePhoneRequest, current_user: dict = Depends(require_driver)):
    email = current_user.get("email", "").lower()
    from firebase_config import db
    driver_ref = db.collection('Driver').document(email)
    driver_ref.update({"phone": request.phone})
    return {"phone": request.phone}

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url='/welcome')

@router.post("/api/driver/search_trips")
async def search_trips(request: Request, current_user: dict = Depends(require_driver)):
    data = await request.json()
    driver_from = data.get('from')
    if not driver_from:
        raise HTTPException(status_code=400, detail="Missing from location")
    
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=500, detail="Google Maps API Key not configured")
    if not RTDB_URL:
        raise HTTPException(status_code=500, detail="RTDB URL not configured")

    geo_url = f'https://maps.googleapis.com/maps/api/geocode/json?address={driver_from}&key={GOOGLE_MAPS_API_KEY}'
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            geo_res = await client.get(geo_url)
        geo_data = geo_res.json()
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to connect to Geocoding API.")
    
    if not geo_data.get('results') or not geo_data['results'][0]:
        raise HTTPException(status_code=400, detail="Could not geocode driver location")
    
    driver_lat = geo_data['results'][0]['geometry']['location']['lat']
    driver_lon = geo_data['results'][0]['geometry']['location']['lng']
    
    trips_ref = rtdb.reference('/trips', url=RTDB_URL)
    trips = trips_ref.order_by_child('status/status').equal_to('pending').get()
    
    if not trips:
        return {'trips': []}

    results = []
    if isinstance(trips, list):
        trips = {str(i): trip for i, trip in enumerate(trips) if trip}

    for trip_id, trip in trips.items():
        if not isinstance(trip, dict):
            continue
        
        cust_lat = trip.get('from_lat')
        cust_lon = trip.get('from_lon')
        if cust_lat is None or cust_lon is None:
            continue
            
        dist = haversine(driver_lat, driver_lon, cust_lat, cust_lon)
        if dist <= 30:
            results.append({
                'trip_id': trip_id,
                'customer_email': trip.get('customer_email', ''),
                'from_location': trip.get('from_location', ''),
                'to_location': trip.get('to_location', ''),
                'date': trip.get('date', ''),
                'created_at': trip.get('created_at', ''),
                'customer_phone': trip.get('customer_phone', ''),
                'status': 'pending',
                'distance_km': round(dist, 2)
            })
    return {'trips': results}

@router.post("/api/driver/accept_trip")
async def accept_trip(req: TripActionRequest, current_user: dict = Depends(require_driver)):
    if not RTDB_URL:
        raise HTTPException(status_code=500, detail="RTDB URL not configured")

    driver_email = current_user.get('email', '').lower()
    driver_data = current_user.get('driver_data', {})
    ist = pytz.timezone('Asia/Kolkata')
    
    trip_ref = rtdb.reference(f'/trips/{req.trip_id}/status', url=RTDB_URL)

    def assign_driver_transaction(current_status):
        if current_status is None:
            return current_status
        if current_status.get('status') == 'pending':
            current_status['status'] = 'driver_assigned'
            current_status['driver_email'] = driver_email
            current_status['driver_name'] = driver_data.get('name', '')
            current_status['driver_phone'] = driver_data.get('phone', '')
            current_status['vehicle_number'] = driver_data.get('vehicle_number', '')
            current_status['assigned_at'] = datetime.now(ist).isoformat()
            return current_status
        return None  # Aborts transaction

    try:
        success = trip_ref.transaction(assign_driver_transaction)
        if success:
            return {'message': 'Trip accepted and assigned to driver.'}
        else:
            raise HTTPException(status_code=409, detail="Conflict: Trip is no longer available.")
    except rtdb.TransactionAbortedError:
        raise HTTPException(status_code=409, detail="Conflict: Trip is no longer available.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Transaction failed due to an internal error.")

@router.post("/api/driver/complete_trip")
async def complete_trip(req: TripActionRequest, current_user: dict = Depends(require_driver)):
    if not RTDB_URL:
        raise HTTPException(status_code=500, detail="RTDB URL not configured")

    driver_email = current_user.get('email', '').lower()
    trip_ref = rtdb.reference(f'/trips/{req.trip_id}/status', url=RTDB_URL)
    ist = pytz.timezone('Asia/Kolkata')

    def complete_trip_txn(current_status):
        if current_status is None:
            return current_status
        if current_status.get('driver_email', '').lower() != driver_email:
            return None
        if current_status.get('status') != 'driver_assigned':
            return None
            
        current_status['status'] = 'trip_completed'
        current_status['completed_at'] = datetime.now(ist).isoformat()
        return current_status

    try:
        success = trip_ref.transaction(complete_trip_txn)
        if success:
            return {'message': 'Trip marked as completed.'}
        else:
            raise HTTPException(status_code=403, detail="Not authorized or trip is not assigned to you.")
    except rtdb.TransactionAbortedError:
        raise HTTPException(status_code=409, detail="Conflict: Could not complete trip.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error completing trip.")

@router.post("/api/driver/release_trip")
async def release_trip(req: TripActionRequest, current_user: dict = Depends(require_driver)):
    if not RTDB_URL:
        raise HTTPException(status_code=500, detail="RTDB URL not configured")

    driver_email = current_user.get('email', '').lower()
    trip_ref = rtdb.reference(f'/trips/{req.trip_id}/status', url=RTDB_URL)

    def release_trip_txn(current_status):
        if current_status is None:
            return current_status
        if current_status.get('driver_email', '').lower() != driver_email:
            return None
        if current_status.get('status') != 'driver_assigned':
            return None
            
        return {'status': 'pending'}

    try:
        success = trip_ref.transaction(release_trip_txn)
        if success:
            return {'message': 'Trip released and set to pending.'}
        else:
            raise HTTPException(status_code=403, detail="Not authorized or trip is not assigned to you.")
    except rtdb.TransactionAbortedError:
        raise HTTPException(status_code=409, detail="Conflict: Could not release trip.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error releasing trip.")

@router.get("/api/geocode")
async def geocode(q: str):
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=500, detail="Google Maps API Key not configured")
    url = f'https://maps.googleapis.com/maps/api/geocode/json?address={q}&key={GOOGLE_MAPS_API_KEY}'
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
    except Exception:
        raise HTTPException(status_code=500, detail="Geocoding API unavailable.")
        
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to geocode address")
    data = resp.json()
    if data.get('status') != 'OK':
        raise HTTPException(status_code=400, detail="Geocoding error from provider.")
    return data

@router.get("/api/driver/assigned_trips")
async def assigned_trips(current_user: dict = Depends(require_driver)):
    if not RTDB_URL:
        raise HTTPException(status_code=500, detail="RTDB URL not configured")

    driver_email = current_user.get('email', '').lower()
    trips_ref = rtdb.reference('/trips', url=RTDB_URL)
    
    # Query for trips where status.driver_email == driver_email
    trips = trips_ref.order_by_child('status/driver_email').equal_to(driver_email).get()
    
    if not trips:
        return {'trips': []}

    results = []
    if isinstance(trips, list):
        trips = {str(i): trip for i, trip in enumerate(trips) if trip}

    for trip_id, trip in trips.items():
        if not isinstance(trip, dict):
            continue
            
        status_info = trip.get('status', {})
        trip_status = status_info.get('status', 'pending')
        
        if trip_status not in ['driver_assigned', 'trip_completed']:
            continue
            
        results.append({
            'trip_id': trip_id,
            'customer_email': trip.get('customer_email', ''),
            'from_location': trip.get('from_location', ''),
            'to_location': trip.get('to_location', ''),
            'date': trip.get('date', ''),
            'created_at': trip.get('created_at', ''),
            'customer_phone': trip.get('customer_phone', ''),
            'status': trip_status
        })
    return {'trips': results}
