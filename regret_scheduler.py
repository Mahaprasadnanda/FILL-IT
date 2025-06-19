from apscheduler.schedulers.background import BackgroundScheduler
from firebase_admin import db
from datetime import datetime
import pytz

def update_pending_to_regret():
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist).date()
    trips_ref = db.reference('/trips', url='https://fill-it-19a6e-default-rtdb.asia-southeast1.firebasedatabase.app/')
    all_trips = trips_ref.get()
    if not all_trips:
        return
    for trip_id, trip in all_trips.items():
        status = trip.get('status', {}).get('status')
        booking_date = trip.get('date')
        if status == 'pending' and booking_date:
            try:
                booking_date_obj = datetime.strptime(booking_date, "%Y-%m-%d").date()
                if booking_date_obj < today:
                    
                    trips_ref.child(trip_id).child('status').update({
                        'status': 'regret',
                        'updated_at': datetime.now(ist).isoformat()
                    })
            except Exception as e:
                print(f"Error updating trip {trip_id}: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(update_pending_to_regret, 'interval', hours=1)  
scheduler.start() 
