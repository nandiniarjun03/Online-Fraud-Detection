import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, precision_recall_curve, auc, precision_score, recall_score, f1_score, roc_auc_score
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
import joblib
import mlflow
import mlflow.sklearn
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "onlinefraud.csv"
MODEL_PATH = PROJECT_ROOT / "models" / "model.pkl"
 
def train_and_compare_models(data_path: str | Path = DATA_PATH):
    mlflow.set_experiment("Online_Fraud_Detection")
   
    # 5% data for fast execution
    df = pd.read_csv(data_path).sample(frac=0.05, random_state=42)
    df.drop(['step', 'nameOrig', 'nameDest', 'isFlaggedFraud'], axis=1, errors='ignore', inplace=True)
    df.dropna(inplace=True)
   
    X = df.drop('isFraud', axis=1)
    y = df['isFraud']
   
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
   
    categorical_features = ['type']
    numerical_features = ['amount', 'oldbalanceOrg', 'newbalanceOrig', 'oldbalanceDest', 'newbalanceDest']
   
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numerical_features),
            ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
        ])
   
    # Define the 3 models
    models = {
        "Logistic_Regression": LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42),
        "Decision_Tree": DecisionTreeClassifier(class_weight='balanced', random_state=42),
        "Random_Forest": RandomForestClassifier(n_estimators=50, class_weight='balanced', random_state=42, n_jobs=-1)
    }
   
    best_pr_auc = 0
    best_model = None
   
    # Train and log each model automatically
    for model_name, classifier in models.items():
        with mlflow.start_run(run_name=model_name):
            print(f"Training {model_name}...")
           
            pipeline = ImbPipeline([
                ('preprocessor', preprocessor),
                ('smote', SMOTE(random_state=42)),
                ('classifier', classifier)
            ])
           
            pipeline.fit(X_train, y_train)
            y_pred = pipeline.predict(X_test)
            y_probs = pipeline.predict_proba(X_test)[:, 1]
           
            precisions, recalls, _ = precision_recall_curve(y_test, y_probs)
            pr_auc = auc(recalls, precisions)
           
            precision = precision_score(y_test, y_pred)
            recall = recall_score(y_test, y_pred)
            f1 = f1_score(y_test, y_pred)
            roc_auc = roc_auc_score(y_test, y_probs)
           
            mlflow.log_metric("Precision", precision)
            mlflow.log_metric("Recall", recall)
            mlflow.log_metric("F1_Score", f1)
            mlflow.log_metric("ROC_AUC", roc_auc)
            mlflow.log_metric("PR_AUC", pr_auc)
            mlflow.sklearn.log_model(
                sk_model=pipeline,
                artifact_path=model_name,
                serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE
            )
 
           
            print(f"{model_name} PR-AUC: {pr_auc:.4f}\n")
           
            # Keep track of the best model for FastAPI
            if pr_auc > best_pr_auc:
                best_pr_auc = pr_auc
                best_model = pipeline
 
    # Overwrite model.pkl with the best performing model (likely Random Forest)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, MODEL_PATH)
    print(f"Best model saved for API with PR-AUC: {best_pr_auc:.4f}")
 
if __name__ == "__main__":
    train_and_compare_models()
 