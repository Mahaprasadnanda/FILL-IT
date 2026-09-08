import sys
import pytest
import os
from unittest.mock import patch, MagicMock

os.environ["RTDB_URL"] = "https://mock-url.firebaseio.com"
os.environ["SESSION_SECRET_KEY"] = "mock_secret"
os.environ["FIREBASE_API_KEY"] = "mock_key"
os.environ["GOOGLE_MAPS_API_KEY"] = "mock_key"
os.environ["RESEND_API_KEY"] = "mock_key"

mock_firestore = MagicMock()
mock_rtdb = MagicMock()
with patch("firebase_admin.firestore.client", return_value=mock_firestore), \
     patch("firebase_admin.initialize_app"), \
     patch("firebase_admin.credentials.Certificate"):
    from firebase_config import db as fb_db
    from main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

@patch("dependencies.auth.verify_id_token")
def test_missing_auth_header(mock_verify):
    response = client.get("/get-profile?email=test@test.com")
    assert response.status_code == 403

@patch("dependencies.auth.verify_id_token")
def test_invalid_token(mock_verify):
    mock_verify.side_effect = Exception("Invalid token")
    response = client.get("/get-profile?email=test@test.com", headers={"Authorization": "Bearer BAD_TOKEN"})
    assert response.status_code == 401

@patch("dependencies.auth.verify_id_token")
@patch("dependencies.db.collection")
def test_customer_access_denied_driver_endpoint(mock_collection, mock_verify):
    mock_verify.return_value = {"email": "customer@test.com", "uid": "123"}
    mock_driver_doc = MagicMock()
    mock_driver_doc.exists = False
    mock_collection.return_value.document.return_value.get.return_value = mock_driver_doc
    
    response = client.get("/api/driver/profile", headers={"Authorization": "Bearer GOOD_TOKEN"})
    assert response.status_code == 403

@patch("dependencies.auth.verify_id_token")
@patch("dependencies.db.collection")
@patch("c_triphistory.db.reference")
def test_driver_access_denied_customer_endpoint(mock_ref, mock_collection, mock_verify):
    mock_verify.return_value = {"email": "driver@test.com", "uid": "123"}
    mock_cust_doc = MagicMock()
    mock_cust_doc.exists = False
    mock_collection.return_value.document.return_value.get.return_value = mock_cust_doc
    
    response = client.get("/get-trip-history?email=driver@test.com", headers={"Authorization": "Bearer GOOD_TOKEN"})
    assert response.status_code == 403

@patch("dependencies.auth.verify_id_token")
@patch("dependencies.db.collection")
@patch("c_triphistory.db.reference")
def test_customer_cannot_modify_others_trip(mock_ref, mock_collection, mock_verify):
    mock_verify.return_value = {"email": "customer1@test.com", "uid": "123"}
    mock_cust_doc = MagicMock()
    mock_cust_doc.exists = True
    mock_collection.return_value.document.return_value.get.return_value = mock_cust_doc
    
    mock_trip_data = {"customer_email": "customer2@test.com", "status": {"status": "pending"}}
    mock_ref.return_value.get.return_value = mock_trip_data
    
    response = client.put("/edit-trip/trip_123", json={"from_location": "A", "to_location": "B", "date": "2026-10-10"}, headers={"Authorization": "Bearer GOOD_TOKEN"})
    assert response.status_code == 403

@patch("dependencies.auth.verify_id_token")
@patch("dependencies.db.collection")
@patch("d_book.rtdb.reference")
def test_driver_cannot_complete_others_trip(mock_ref, mock_collection, mock_verify):
    mock_verify.return_value = {"email": "driver1@test.com", "uid": "123"}
    mock_driver_doc = MagicMock()
    mock_driver_doc.exists = True
    mock_collection.return_value.document.return_value.get.return_value = mock_driver_doc
    
    # Simulate transaction evaluation
    def txn_side_effect(txn_func):
        # txn_func will return None if authorization fails
        res = txn_func({"status": "driver_assigned", "driver_email": "driver2@test.com"})
        return res is not None

    mock_ref.return_value.transaction.side_effect = txn_side_effect
    
    response = client.post("/api/driver/complete_trip", json={"trip_id": "trip_123"}, headers={"Authorization": "Bearer GOOD_TOKEN"})
    assert response.status_code == 403

@patch("dependencies.auth.verify_id_token")
@patch("dependencies.db.collection")
@patch("d_book.rtdb.reference")
def test_race_condition_assignment(mock_ref, mock_collection, mock_verify):
    mock_verify.return_value = {"email": "driver1@test.com", "uid": "123"}
    mock_driver_doc = MagicMock()
    mock_driver_doc.exists = True
    mock_collection.return_value.document.return_value.get.return_value = mock_driver_doc
    
    mock_ref.return_value.transaction.return_value = False
    
    response = client.post("/api/driver/accept_trip", json={"trip_id": "trip_123"}, headers={"Authorization": "Bearer GOOD_TOKEN"})
    assert response.status_code == 409
    
@patch("dependencies.auth.verify_id_token")
@patch("dependencies.db.collection")
@patch("c_triphistory.db.reference")
@patch("httpx.AsyncClient.get")
def test_edit_trip_location_change_geocodes(mock_get, mock_ref, mock_collection, mock_verify):
    mock_verify.return_value = {"email": "customer@test.com", "uid": "123"}
    mock_cust_doc = MagicMock()
    mock_cust_doc.exists = True
    mock_collection.return_value.document.return_value.get.return_value = mock_cust_doc
    
    mock_trip_data = {
        "customer_email": "customer@test.com", 
        "from_location": "A",
        "status": {"status": "pending"}
    }
    mock_ref.return_value.get.return_value = mock_trip_data
    mock_ref.return_value.transaction.return_value = True
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [{"geometry": {"location": {"lat": 10.0, "lng": 20.0}}}]
    }
    mock_get.return_value = mock_response

    response = client.put("/edit-trip/trip_123", json={"from_location": "B", "to_location": "C", "date": "2026-10-10"}, headers={"Authorization": "Bearer GOOD_TOKEN"})
    assert response.status_code == 200
    mock_get.assert_called_once() 

if __name__ == "__main__":
    pytest.main(["-v", "test_app.py"])
