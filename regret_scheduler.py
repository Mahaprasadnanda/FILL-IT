from apscheduler.schedulers.background import BackgroundScheduler
from firebase_admin import db
from datetime import datetime
import pytz
import os

RTDB_URL = os.getenv("RTDB_URL", "https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/")

def update_pending_to_regret():
    try:
        ist = pytz.timezone('Asia/Kolkata')
        today = datetime.now(ist).date()
        trips_ref = db.reference('/trips', url=RTDB_URL)
        all_trips = trips_ref.get()
        if not all_trips:
            return
        
        # Handle case where trips is a list instead of dict
        if isinstance(all_trips, list):
            all_trips = {str(i): trip for i, trip in enumerate(all_trips) if trip}

        for trip_id, trip in all_trips.items():
            if not isinstance(trip, dict):
                continue

            try:
                status = trip.get('status', {}).get('status')
                booking_date = trip.get('date')
                if status == 'pending' and booking_date:
                    try:
                        if '-' in str(booking_date):
                            booking_date_obj = datetime.strptime(str(booking_date), "%Y-%m-%d").date()
                        else:
                            booking_date_obj = datetime.strptime(str(booking_date), "%d/%m/%Y").date()
                    except ValueError:
                        continue # Skip invalid dates silently to avoid breaking the job
                    
                    if booking_date_obj < today:
                        trips_ref.child(trip_id).child('status').update({
                            'status': 'regret',
                            'updated_at': datetime.now(ist).isoformat()
                        })
            except Exception as e:
                print(f"Error updating trip {trip_id}: {e}")
    except Exception as outer_e:
        print(f"Scheduler outer error: {outer_e}")

scheduler = BackgroundScheduler()
scheduler.add_job(update_pending_to_regret, 'interval', hours=1)  
scheduler.start() 
