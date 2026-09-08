from apscheduler.schedulers.background import BackgroundScheduler
from firebase_admin import db
from datetime import datetime
import pytz
import os

RTDB_URL = os.getenv("RTDB_URL")

def update_pending_to_regret():
    if not RTDB_URL:
        return
        
    try:
        ist = pytz.timezone('Asia/Kolkata')
        today = datetime.now(ist).date()
        trips_ref = db.reference('/trips', url=RTDB_URL)
        pending_trips = trips_ref.order_by_child('status/status').equal_to('pending').get()
        if not pending_trips:
            return
        
        if isinstance(pending_trips, list):
            pending_trips = {str(i): trip for i, trip in enumerate(pending_trips) if trip}

        for trip_id, trip in pending_trips.items():
            if not isinstance(trip, dict):
                continue

            try:
                booking_date = trip.get('date')
                if booking_date:
                    try:
                        if '-' in str(booking_date):
                            booking_date_obj = datetime.strptime(str(booking_date), "%Y-%m-%d").date()
                        else:
                            booking_date_obj = datetime.strptime(str(booking_date), "%d/%m/%Y").date()
                    except ValueError:
                        continue 
                    
                    if booking_date_obj < today:
                        # Update status using transaction to ensure it's still pending
                        def regret_txn(current_status):
                            if current_status is None:
                                return current_status
                            if current_status.get('status') == 'pending':
                                current_status['status'] = 'regret'
                                current_status['updated_at'] = datetime.now(ist).isoformat()
                                return current_status
                            return None
                        
                        try:
                            trips_ref.child(f"{trip_id}/status").transaction(regret_txn)
                        except db.TransactionAbortedError:
                            pass # Probably no longer pending
            except Exception:
                pass # Silently skip one failed trip
    except Exception:
        pass # Silently skip job failure

scheduler = BackgroundScheduler()
scheduler.add_job(update_pending_to_regret, 'interval', hours=1, coalesce=True, max_instances=1)  
scheduler.start() 
