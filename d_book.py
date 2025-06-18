from fastapi import APIRouter, Request, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import firebase_admin
from firebase_admin import firestore
from firebase_admin import auth
from typing import Optional, Dict, Any
import json
from firebase_config import db
import requests
from datetime import datetime
import math
from firebase_admin import db as rtdb

router = APIRouter()

RTDB_URL = 'https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/'
GOOGLE_MAPS_API_KEY = 'AIzaSyAOXzRX48gcKoX4ndad2hcSPQ7hxFfdSJs'

# Helper: Haversine formula for distance in km
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

@router.get("/d_home", response_class=HTMLResponse)
async def d_home(request: Request):
    with open("d_home.html", "r") as f:
        content = f.read()
    return HTMLResponse(content=content)

@router.get("/api/driver/profile")
async def get_driver_profile(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    id_token = authorization.replace("Bearer ", "").strip()
    try:
        decoded_token = auth.verify_id_token(id_token)
        email = decoded_token.get("email", "").lower()
        driver_ref = db.collection('Driver').document(email)
        driver = driver_ref.get()
        if not driver.exists:
            raise HTTPException(status_code=404, detail="Driver not found")
        driver_data: Dict[str, Any] = driver.to_dict() or {}
        return {
            "name": driver_data.get("name", ""),
            "email": driver_data.get("email", ""),
            "phone": driver_data.get("phone", "")
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {str(e)}")

@router.post("/api/driver/update_phone")
async def update_phone(request: Request, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    id_token = authorization.replace("Bearer ", "").strip()
    try:
        decoded_token = auth.verify_id_token(id_token)
        email = decoded_token.get("email", "").lower()
        data = await request.json()
        new_phone = data.get("phone")
        if not new_phone:
            raise HTTPException(status_code=400, detail="Phone number is required")
        driver_ref = db.collection('Driver').document(email)
        driver = driver_ref.get()
        if not driver.exists:
            raise HTTPException(status_code=404, detail="Driver not found")
        driver_ref.update({"phone": new_phone})
        return {"phone": new_phone}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request body")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {str(e)}")

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url='/welcome')

@router.post("/api/driver/search_trips")
async def search_trips(request: Request, authorization: Optional[str] = Header(None)):
    data = await request.json()
    driver_from = data.get('from')
    if not driver_from:
        raise HTTPException(status_code=400, detail="Missing from location")
    # Geocode driver location using Google Maps
    geo_url = f'https://maps.googleapis.com/maps/api/geocode/json?address={driver_from}&key={GOOGLE_MAPS_API_KEY}'
    geo_res = requests.get(geo_url)
    geo_data = geo_res.json()
    if not geo_data.get('results') or not geo_data['results'][0]:
        raise HTTPException(status_code=400, detail="Could not geocode driver location")
    driver_lat = geo_data['results'][0]['geometry']['location']['lat']
    driver_lon = geo_data['results'][0]['geometry']['location']['lng']
    # Fetch all trips (no date filter)
    trips_ref = rtdb.reference('/trips', url=RTDB_URL)
    trips = trips_ref.get() or {}
    if isinstance(trips, list):
        trips = {str(i): trip for i, trip in enumerate(trips) if trip}
    results = []
    for trip_id, trip in trips.items():
        if not isinstance(trip, dict):
            continue
        status = trip['status'] if 'status' in trip and isinstance(trip['status'], dict) else {}
        trip_status = status['status'] if 'status' in status else 'pending'
        if trip_status not in ['pending']:
            continue
        # Geocode customer from location using Google Maps
        cust_from = trip['from_location'] if 'from_location' in trip else ''
        cust_geo_url = f'https://maps.googleapis.com/maps/api/geocode/json?address={cust_from}&key={GOOGLE_MAPS_API_KEY}'
        cust_geo_res = requests.get(cust_geo_url)
        cust_geo_data = cust_geo_res.json()
        if not cust_geo_data.get('results') or not cust_geo_data['results'][0]:
            continue
        cust_lat = cust_geo_data['results'][0]['geometry']['location']['lat']
        cust_lon = cust_geo_data['results'][0]['geometry']['location']['lng']
        dist = haversine(driver_lat, driver_lon, cust_lat, cust_lon)
        if dist <= 30:
            customer_email = trip['customer_email'] if 'customer_email' in trip else ''
            customer_phone = trip['customer_phone'] if 'customer_phone' in trip else ''
            # If phone not in RTDB, fetch from Firestore
            if not customer_phone and customer_email:
                try:
                    customer_doc = firestore.client().collection('Customer').document(customer_email).get()
                    if customer_doc.exists:
                        customer_data = customer_doc.to_dict()
                        customer_phone = customer_data.get('phone', '')
                except Exception:
                    customer_phone = ''
            results.append({
                'trip_id': trip_id,
                'customer_email': customer_email,
                'from_location': cust_from,
                'to_location': trip['to_location'] if 'to_location' in trip else '',
                'date': trip['date'] if 'date' in trip else '',
                'created_at': trip['created_at'] if 'created_at' in trip else '',
                'customer_phone': customer_phone,
                'status': trip_status
            })
    return {'trips': results}

@router.post("/api/driver/accept_trip")
async def accept_trip(request: Request, authorization: Optional[str] = Header(None)):
    data = await request.json()
    trip_id = data.get('trip_id')
    if not trip_id:
        raise HTTPException(status_code=400, detail="Missing trip_id")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    id_token = authorization.replace("Bearer ", "").strip()
    decoded_token = auth.verify_id_token(id_token)
    driver_email = decoded_token.get('email', '').lower()
    # Get driver details from Firestore
    driver_doc = db.collection('Driver').document(driver_email).get()
    if not driver_doc.exists:
        raise HTTPException(status_code=404, detail="Driver not found")
    driver_data = driver_doc.to_dict()
    # Update trip in RTDB
    trip_ref = rtdb.reference(f'/trips/{trip_id}', url=RTDB_URL)
    trip_ref.child('status').set({
        'status': 'driver_assigned',
        'driver_email': driver_email,
        'driver_name': driver_data.get('name', ''),
        'driver_phone': driver_data.get('phone', ''),
        'vehicle_number': driver_data.get('vehicle_number', ''),
        'assigned_at': datetime.now().isoformat()
    })
    return {'message': 'Trip accepted and assigned to driver.'}

@router.post("/api/driver/complete_trip")
async def complete_trip(request: Request, authorization: Optional[str] = Header(None)):
    data = await request.json()
    trip_id = data.get('trip_id')
    if not trip_id:
        raise HTTPException(status_code=400, detail="Missing trip_id")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    # Update trip in RTDB
    trip_ref = rtdb.reference(f'/trips/{trip_id}', url=RTDB_URL)
    trip_ref.child('status').update({
        'status': 'trip_completed',
        'completed_at': datetime.now().isoformat()
    })
    return {'message': 'Trip marked as completed.'}

@router.get("/api/geocode")
async def geocode(q: str):
    url = f'https://maps.googleapis.com/maps/api/geocode/json?address={q}&key={GOOGLE_MAPS_API_KEY}'
    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to geocode address")
    data = resp.json()
    if data.get('status') != 'OK':
        raise HTTPException(status_code=400, detail=f"Geocoding error: {data.get('status')}")
    return data

@router.get("/api/driver/assigned_trips")
async def assigned_trips(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    id_token = authorization.replace("Bearer ", "").strip()
    decoded_token = auth.verify_id_token(id_token)
    driver_email = decoded_token.get('email', '').lower()
    trips_ref = rtdb.reference('/trips', url=RTDB_URL)
    trips = trips_ref.get() or {}
    if isinstance(trips, list):
        trips = {str(i): trip for i, trip in enumerate(trips) if trip}
    results = []
    for trip_id, trip in trips.items():
        if not isinstance(trip, dict):
            continue
        status = trip['status'] if 'status' in trip and isinstance(trip['status'], dict) else {}
        trip_status = status['status'] if 'status' in status else 'pending'
        if trip_status not in ['driver_assigned', 'trip_completed']:
            continue
        if status.get('driver_email', '').lower() != driver_email:
            continue
        if trip_status in ['regret', 'rejected']:
            continue
        customer_email = trip['customer_email'] if 'customer_email' in trip else ''
        customer_phone = trip['customer_phone'] if 'customer_phone' in trip else ''
        if not customer_phone and customer_email:
            try:
                customer_doc = firestore.client().collection('Customer').document(customer_email).get()
                if customer_doc.exists:
                    customer_data = customer_doc.to_dict()
                    customer_phone = customer_data.get('phone', '')
            except Exception:
                customer_phone = ''
        results.append({
            'trip_id': trip_id,
            'customer_email': customer_email,
            'from_location': trip['from_location'] if 'from_location' in trip else '',
            'to_location': trip['to_location'] if 'to_location' in trip else '',
            'date': trip['date'] if 'date' in trip else '',
            'created_at': trip['created_at'] if 'created_at' in trip else '',
            'customer_phone': customer_phone,
            'status': trip_status
        })
    return {'trips': results}

@router.post("/api/driver/release_trip")
async def release_trip(request: Request, authorization: Optional[str] = Header(None)):
    data = await request.json()
    trip_id = data.get('trip_id')
    if not trip_id:
        raise HTTPException(status_code=400, detail="Missing trip_id")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    # Set trip status to pending and remove driver info
    trip_ref = rtdb.reference(f'/trips/{trip_id}', url=RTDB_URL)
    trip_ref.child('status').set({
        'status': 'pending'
    })
    return {'message': 'Trip released and set to pending.'}