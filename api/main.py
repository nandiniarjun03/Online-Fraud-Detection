from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import joblib
import pandas as pd
from pathlib import Path
 
app = FastAPI()
 
# Check if model exists (for local), else use a Dummy for GitHub Actions (CI)
model_path = Path(__file__).resolve().parent.parent / "models" / "model.pkl"
if model_path.exists():
    model = joblib.load(model_path)
else:
    class DummyModel:
        def predict(self, x): return [0]
        def predict_proba(self, x): return [[1.0, 0.0]]
    model = DummyModel()
 
class TransactionData(BaseModel):
    type: str
    amount: float
    oldbalanceOrg: float
    newbalanceOrig: float
    oldbalanceDest: float
    newbalanceDest: float
 
@app.get("/health")
def health_check():
    return {"status": "healthy"}
 
@app.post("/predict")
def predict_transaction(data: TransactionData):
    try:
        input_data = pd.DataFrame([data.model_dump()])
        
        prediction = model.predict(input_data)
        probability = model.predict_proba(input_data)[0][1]
        
        return {
            "predicted_class": int(prediction[0]),
            "fraud_probability": float(probability)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
 