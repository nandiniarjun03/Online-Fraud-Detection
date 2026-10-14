from fastapi.testclient import TestClient
from main import app
 
client = TestClient(app)
 
def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
 
def test_predict_transaction():
    payload = {
        "type": "PAYMENT",
        "amount": 9839.64,
        "oldbalanceOrg": 170136.0,
        "newbalanceOrig": 160296.36,
        "oldbalanceDest": 0.0,
        "newbalanceDest": 0.0
    }
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    assert "predicted_class" in response.json()
    assert "fraud_probability" in response.json()
 