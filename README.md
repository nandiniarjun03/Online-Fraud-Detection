# Online Fraud Transaction Detection

An end-to-end fraud detection project using scikit-learn, SMOTE, MLflow, and FastAPI.

## Requirements

- Python 3.12
- The fraud dataset at `data/onlinefraud.csv`

The dataset, trained model, MLflow tracking database, and MLflow artifacts are excluded from Git. Obtain the dataset separately and place it at `data/onlinefraud.csv` before training.

## Setup and run

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Train and compare models:

```bash
python src/train.py
```

This logs the model runs to MLflow and saves the best model to `models/model.pkl`.

Run the API from the project root:

```bash
python -m uvicorn main:app --app-dir api --host 127.0.0.1 --port 8765
```

Run the API tests:

```bash
python -m pip install pytest httpx
python -m pytest api/test_main.py
```
