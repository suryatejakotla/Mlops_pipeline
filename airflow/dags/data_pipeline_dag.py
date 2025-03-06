import json
import pandas as pd
import uuid
import os
import pickle
import random
import logging
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from sklearn.preprocessing import StandardScaler, LabelEncoder
from feast import FeatureStore

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Directory and file paths
MODEL_PATH = "/Users/nc25577_suryateja/Documents/air_pro/model/fraud_detection_model.pkl"
SCALER_PATH = "/Users/nc25577_suryateja/Documents/air_pro/model/scaler.pkl"
TEMP_DIR = "/Users/nc25577_suryateja/Documents/air_pro/input_files"
FEAST_REPO_PATH = "/Users/nc25577_suryateja/Documents/air_pro/feature_repo/feature_repo"

os.makedirs(TEMP_DIR, exist_ok=True, mode=0o777)

# Feast Feature Store
store = FeatureStore(repo_path=FEAST_REPO_PATH)

# DAG Functions
def load_resources(**kwargs):
    logger.info("Loading model and scaler...")
    try:
        if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
            raise FileNotFoundError(f"Model ({MODEL_PATH}) or scaler ({SCALER_PATH}) not found.")
        with open(MODEL_PATH, 'rb') as model_file, open(SCALER_PATH, 'rb') as scaler_file:
            model = pickle.load(model_file)
            scaler = pickle.load(scaler_file)
        logger.info("Model and scaler loaded successfully.")
        return {"model": model, "scaler": scaler}
    except Exception as e:
        logger.error(f"Failed to load resources: {str(e)}")
        raise

def process_input_file(**kwargs):
    logger.info(f"Received kwargs: {kwargs}")
    conf = kwargs.get('conf', {})
    if isinstance(conf, dict):
        file_path = conf.get('file_path')
    else:
        params = kwargs.get('params', {})
        file_path = params.get('file_path') if isinstance(params, dict) else None

    if not file_path:
        file_path = os.path.join(TEMP_DIR, "uploaded_file")
        logger.warning(f"No file_path in conf; defaulting to {file_path}")
    
    logger.info(f"Processing input file at {file_path}")
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if os.stat(file_path).st_size == 0:
        logger.error(f"Input file {file_path} is empty")
        raise ValueError(f"Input file {file_path} is empty")
    
    try:
        file_extension = os.path.splitext(file_path)[1].lower()
        if not file_extension:
            with open(file_path, 'r') as file:
                first_line = file.read(1024)
                if first_line.strip().startswith('{') or first_line.strip().startswith('['):
                    file_extension = '.json'
        
        if file_extension == '.json':
            with open(file_path, "r") as file:
                data = json.load(file)
            logger.info(f"Loaded JSON data: {data}")
            if "session_id" in data:  # Finbox
                df = pd.DataFrame([{
                    "UserId": random.randint(1000000, 9999999),
                    "RealmId": data.get("session_id", str(uuid.uuid4())),
                    "Account_number": acc.get("data", {}).get("account_details", {}).get("account_number", ""),
                    "Date": txn.get("date", ""),
                    "Amount": float(txn.get("amount", 0)) * (-1 if txn.get("transaction_type", "").lower() == "debit" else 1),
                    "Balance": float(txn.get("balance", 0)),
                    "Narration": txn.get("transaction_note", ""),
                    "Type": txn.get("transaction_type", "").lower()
                } for acc in data.get("accounts", []) for txn in acc.get("data", {}).get("transactions", [])])
            elif "data" in data and isinstance(data["data"], list):  # OneMoney
                df = pd.DataFrame([{
                    "UserId": random.randint(1000000, 9999999),
                    "RealmId": acc.get("linkedAccRef", str(uuid.uuid4())),
                    "Account_number": acc.get("maskedAccNumber", ""),
                    "Date": txn.get("valueDate", ""),
                    "Amount": float(txn.get("amount", 0)) * (-1 if txn.get("type", "").lower() == "debit" else 1),
                    "Balance": float(txn.get("currentBalance", 0)),
                    "Narration": txn.get("narration", ""),
                    "Type": txn.get("type", "").lower()
                } for acc in data.get("data", []) for txn in acc.get("Transactions", {}).get("Transaction", [])])
            else:  # Perfios
                user_id = data.get("userId", random.randint(1000000, 9999999))
                realm_id = data.get("realmId", str(uuid.uuid4()))
                transactions = []
                for key in ["accountXns", "report"]:
                    account_xns = data.get(key, {}).get("accountXns") if key == "report" else data.get(key)
                    if account_xns:
                        for acc in account_xns:
                            for txn in acc.get("xns", []):
                                transactions.append({
                                    "UserId": user_id,
                                    "RealmId": realm_id,
                                    "Account_number": acc.get("accountNo", "Unknown"),
                                    "Date": txn.get("date", "Unknown"),
                                    "Amount": txn.get("amount", 0),
                                    "Balance": txn.get("balance", 0),
                                    "Narration": txn.get("narration", "Unknown"),
                                    "Type": "Credit" if txn.get("amount", 0) > 0 else "Debit"
                                })
                df = pd.DataFrame(transactions)
        elif file_extension == '.xlsx':  # ScoreMe
            user_id = file_path.split("/")[-1].split("_")[0]
            realm_id = str(uuid.uuid4())
            xls = pd.ExcelFile(file_path)
            account_number = pd.read_excel(xls, sheet_name="Account Details", header=None).iloc[9, 6]
            df = pd.read_excel(xls, sheet_name="Bank Statement", skiprows=4)
            logger.info(f"Loaded Excel data with {len(df)} rows")
            df = df.rename(columns={"Date": "Date", "Particulars": "Narration", "Debit": "Debit", "Credit": "Credit", "Balance": "Balance"})
            df["Debit"] = pd.to_numeric(df["Debit"], errors='coerce').fillna(0)
            df["Credit"] = pd.to_numeric(df["Credit"], errors='coerce').fillna(0)
            df["Amount"] = df["Credit"] - df["Debit"]
            df["Type"] = df.apply(lambda row: "Credit" if row["Credit"] > 0 else "Debit", axis=1)
            df["Balance"] = pd.to_numeric(df["Balance"], errors='coerce').abs()
            df.insert(0, "UserId", user_id)
            df.insert(1, "RealmId", realm_id)
            df.insert(2, "Account_number", account_number)
            df = df[["UserId", "RealmId", "Account_number", "Date", "Amount", "Balance", "Narration", "Type"]]
        else:
            logger.error(f"Unsupported or unrecognized file type: {file_path} (extension: {file_extension})")
            raise ValueError(f"Unsupported or unrecognized file type: {file_path} (extension: {file_extension})")
        
        if df.empty:
            logger.error(f"No data extracted from file {file_path}. Check file content or format.")
            raise ValueError(f"No data extracted from file {file_path}. Check file content or format.")
        
        df['event_timestamp'] = pd.Timestamp.now()
        feature_data = df[["RealmId", "UserId", "Account_number", "Date", "Amount", "Balance", "Narration", "Type", "event_timestamp"]]
        store.write_to_online_store(feature_view_name="fraud_features", df=feature_data)
        kwargs['ti'].xcom_push(key='realm_ids', value=df['RealmId'].unique().tolist())
        return True
    except Exception as e:
        logger.error(f"Error processing input file: {str(e)}")
        raise

def engineer_features(ti, **kwargs):
    logger.info("Engineering features from Feast...")
    try:
        realm_ids = ti.xcom_pull(task_ids='process_input_file', key='realm_ids')
        if not realm_ids:
            logger.error("No RealmIds found in XCom from process_input_file")
            raise ValueError("No RealmIds found in XCom from process_input_file")
        
        entity_df = pd.DataFrame({"RealmId": realm_ids, "event_timestamp": [pd.Timestamp.now()] * len(realm_ids)})
        df = store.get_online_features(
            features=[
                "fraud_features:UserId",
                "fraud_features:Account_number",
                "fraud_features:Date",
                "fraud_features:Amount",
                "fraud_features:Balance",
                "fraud_features:Narration",
                "fraud_features:Type"
            ],
            entity_rows=[{"RealmId": rid} for rid in realm_ids]
        ).to_df()
        
        logger.info(f"Loaded {len(df)} rows from Feast online store")
        if df.empty:
            logger.error("No data retrieved from Feast online store")
            raise ValueError("No data retrieved from Feast online store")
        
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Hour'] = df['Date'].dt.hour
        df['Day'] = df['Date'].dt.day
        df['Month'] = df['Date'].dt.month
        df['DayOfWeek'] = df['Date'].dt.dayofweek
        df['IsWeekend'] = df['DayOfWeek'].isin([5, 6]).astype(int)
        df['AmountAbs'] = abs(df['Amount'])
        df['IsNegative'] = (df['Amount'] < 0).astype(int)
        df['BalanceAfterTxn'] = df['Balance'] + df['Amount']
        df['BalanceToAmountRatio'] = df['Balance'] / (df['AmountAbs'] + 1e-5)
        df['RealmId'] = LabelEncoder().fit_transform(df['RealmId'])
        df['Type'] = LabelEncoder().fit_transform(df['Type'])
        user_stats = df.groupby('RealmId').agg({
            'Amount': ['count', 'mean', 'std'],
            'Balance': ['mean', 'std']
        }).fillna(0)
        user_stats.columns = ['txn_count', 'amount_mean', 'amount_std', 'balance_mean', 'balance_std']
        df = df.merge(user_stats.reset_index(), on='RealmId', how='left')
        
        output_path = os.path.join(TEMP_DIR, "engineered_df.csv")
        df.to_csv(output_path, index=False)
        logger.info(f"Engineered features saved to {output_path} with {len(df)} rows")
        return output_path
    except Exception as e:
        logger.error(f"Error in feature engineering: {str(e)}")
        raise

def prepare_prediction_data(ti, **kwargs):
    logger.info("Preparing data for prediction...")
    try:
        input_path = ti.xcom_pull(task_ids='engineer_features')
        if not input_path or not os.path.exists(input_path):
            raise FileNotFoundError(f"Engineered data file not found at {input_path}")
        df = pd.read_csv(input_path)
        features = ['Hour', 'Day', 'Month', 'DayOfWeek', 'IsWeekend', 'Amount', 'AmountAbs', 'IsNegative', 
                    'Balance', 'BalanceAfterTxn', 'BalanceToAmountRatio', 'Type', 'txn_count', 'amount_mean', 
                    'amount_std', 'balance_mean', 'balance_std']
        X = df[features]
        output_path = os.path.join(TEMP_DIR, "prediction_data.csv")
        X.to_csv(output_path, index=False)
        logger.info(f"Prediction data saved to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error preparing prediction data: {str(e)}")
        raise

def predict_fraud(ti, **kwargs):
    logger.info("Making fraud predictions...")
    try:
        resources = ti.xcom_pull(task_ids='load_resources')
        if not resources:
            raise ValueError("Resources not loaded from load_resources task.")
        model, scaler = resources["model"], resources["scaler"]
        input_path = ti.xcom_pull(task_ids='prepare_prediction_data')
        if not input_path or not os.path.exists(input_path):
            raise FileNotFoundError(f"Prediction data file not found at {input_path}")
        X = pd.read_csv(input_path)
        X_scaled = scaler.transform(X)
        predictions = model.predict(X_scaled)
        prediction_proba = model.predict_proba(X_scaled)[:, 1]
        output_path = os.path.join(TEMP_DIR, "predictions.pkl")
        with open(output_path, 'wb') as f:
            pickle.dump({"predictions": predictions, "prediction_proba": prediction_proba}, f)
        logger.info(f"Predictions saved to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error in prediction: {str(e)}")
        raise

def generate_summary(ti, **kwargs):
    logger.info("Generating summary...")
    try:
        input_df_path = ti.xcom_pull(task_ids='engineer_features')
        input_pred_path = ti.xcom_pull(task_ids='predict_fraud')
        if not input_df_path or not os.path.exists(input_df_path):
            raise FileNotFoundError(f"Engineered data file not found at {input_df_path}")
        if not input_pred_path or not os.path.exists(input_pred_path):
            raise FileNotFoundError(f"Predictions file not found at {input_pred_path}")
        df = pd.read_csv(input_df_path)
        with open(input_pred_path, 'rb') as f:
            pred_data = pickle.load(f)
        predictions, prediction_proba = pred_data["predictions"], pred_data["prediction_proba"]
        df['FraudPrediction'] = predictions
        df['FraudProbability'] = prediction_proba
        total_transactions = int(len(df))
        fraudulent_transactions = int(df['FraudPrediction'].sum())
        fraud_percentage = float((fraudulent_transactions / total_transactions) * 100 if total_transactions > 0 else 0)
        account_data = df.groupby('Account_number').agg(
            fraud_count=('FraudPrediction', 'sum'),
            total_count=('FraudPrediction', 'count')
        ).reset_index()
        account_data['fraud_percentage'] = account_data['fraud_count'] / account_data['total_count'] * 100
        fraud_threshold = 50.0
        fraudulent_accounts = account_data[account_data['fraud_percentage'] > fraud_threshold]['Account_number'].tolist()
        fraudulent_percs = [float(perc) for perc in account_data[account_data['fraud_percentage'] > fraud_threshold]['fraud_percentage'].tolist()]
        non_fraudulent_accounts = account_data[account_data['fraud_percentage'] <= fraud_threshold]['Account_number'].tolist()
        non_fraudulent_percs = [float(perc) for perc in account_data[account_data['fraud_percentage'] <= fraud_threshold]['fraud_percentage'].tolist()]
        summary = {
            "total_transactions": total_transactions,
            "fraudulent_transactions": fraudulent_transactions,
            "fraud_percentage": fraud_percentage,
            "highlighted_accounts": [(acc, f"{perc:.2f}") for acc, perc in zip(fraudulent_accounts, fraudulent_percs)] or [("None", "0.00")],
            "other_accounts": [(acc, f"{perc:.2f}") for acc, perc in zip(non_fraudulent_accounts, non_fraudulent_percs)] or [("None", "0.00")]
        }
        logger.info(f"Summary before serialization: {summary}")
        output_path = os.path.join(TEMP_DIR, f"summary_{ti.dag_run.run_id}.json")
        with open(output_path, 'w') as f:
            json.dump(summary, f)
        logger.info(f"Summary saved to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        raise

# Define Airflow DAG
default_args = {
    'owner': 'airflow',
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=30)
}

with DAG(
    'fraud_detection_processing_dag',
    start_date=datetime(2025, 2, 23),
    schedule_interval=None,
    catchup=False,
    default_args=default_args
) as processing_dag:
    t1 = PythonOperator(
        task_id='load_resources',
        python_callable=load_resources,
        provide_context=True
    )
    t2 = PythonOperator(
        task_id='process_input_file',
        python_callable=process_input_file,
        provide_context=True
    )
    t3 = PythonOperator(
        task_id='engineer_features',
        python_callable=engineer_features,
        provide_context=True
    )
    t4 = PythonOperator(
        task_id='prepare_prediction_data',
        python_callable=prepare_prediction_data,
        provide_context=True
    )
    t5 = PythonOperator(
        task_id='predict_fraud',
        python_callable=predict_fraud,
        provide_context=True
    )
    t6 = PythonOperator(
        task_id='generate_summary',
        python_callable=generate_summary,
        provide_context=True
    )

    t1 >> t2 >> t3 >> t4 >> t5 >> t6