import sys
import pytest
from unittest.mock import patch, MagicMock

# Mock firebase configs BEFORE importing main
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
    
    # Mock the trip owned by customer2
    mock_trip_data = {"customer_email": "customer2@test.com", "status": {"status": "pending"}}
    mock_ref.return_value.get.return_value = mock_trip_data
    
    response = client.put("/edit-trip/trip_123", json={"from_location": "A", "to_location": "B", "date": "2026-10-10"}, headers={"Authorization": "Bearer GOOD_TOKEN"})
    assert response.status_code == 403
    assert "Not authorized" in response.text

@patch("dependencies.auth.verify_id_token")
@patch("dependencies.db.collection")
@patch("d_book.rtdb.reference")
def test_driver_cannot_complete_others_trip(mock_ref, mock_collection, mock_verify):
    mock_verify.return_value = {"email": "driver1@test.com", "uid": "123"}
    mock_driver_doc = MagicMock()
    mock_driver_doc.exists = True
    mock_collection.return_value.document.return_value.get.return_value = mock_driver_doc
    
    # Mock the trip assigned to driver2
    mock_trip_data = {
        "status": {
            "status": "driver_assigned",
            "driver_email": "driver2@test.com"
        }
    }
    mock_ref.return_value.get.return_value = mock_trip_data
    
    response = client.post("/api/driver/complete_trip", json={"trip_id": "trip_123"}, headers={"Authorization": "Bearer GOOD_TOKEN"})
    assert response.status_code == 403
    assert "Not authorized" in response.text

@patch("dependencies.auth.verify_id_token")
@patch("dependencies.db.collection")
@patch("d_book.rtdb.reference")
def test_race_condition_assignment(mock_ref, mock_collection, mock_verify):
    mock_verify.return_value = {"email": "driver1@test.com", "uid": "123"}
    mock_driver_doc = MagicMock()
    mock_driver_doc.exists = True
    mock_collection.return_value.document.return_value.get.return_value = mock_driver_doc
    
    # We will mock transaction behavior to simulate conflict
    mock_ref.return_value.transaction.return_value = False
    
    response = client.post("/api/driver/accept_trip", json={"trip_id": "trip_123"}, headers={"Authorization": "Bearer GOOD_TOKEN"})
    assert response.status_code == 409
    assert "Conflict" in response.text

if __name__ == "__main__":
    pytest.main(["-v", "test_app.py"])
