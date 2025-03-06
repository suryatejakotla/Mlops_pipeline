import os
import json
import time
import requests
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# FastAPI setup
app = FastAPI()
templates = Jinja2Templates(directory="/Users/nc25577_suryateja/Documents/air_pro/app/templates")

# Directory and API paths
TEMP_DIR = "/Users/nc25577_suryateja/Documents/air_pro/input_files"
AIRFLOW_API_URL = "http://localhost:8080/api/v1/dags/fraud_detection_processing_dag/dagRuns"
AIRFLOW_AUTH = ("admin", "admin")

os.makedirs(TEMP_DIR, exist_ok=True)

# FastAPI Endpoints
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze_file(request: Request, file: UploadFile = File(...)):
    start_time = time.time()

    # Validate file type
    if not (file.filename.endswith('.json') or file.filename.endswith('.xlsx')):
        raise HTTPException(status_code=400, detail="Only JSON and XLSX files are supported.")

    # Save uploaded file
    file_path = os.path.join(TEMP_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    logger.info(f"File uploaded: {file_path}")

    # Trigger Airflow DAG
    dag_run_id = f"manual__{int(time.time())}"
    summary_path = os.path.join(TEMP_DIR, f"summary_{dag_run_id}.json")

    payload = {
        "dag_run_id": dag_run_id,
        "conf": {"file_path": file_path}
    }
    try:
        response = requests.post(AIRFLOW_API_URL, json=payload, auth=AIRFLOW_AUTH)
        response.raise_for_status()
        logger.info(f"DAG triggered with run_id: {dag_run_id}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to trigger DAG: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger DAG: {str(e)}")

    # Wait for DAG to produce the summary file
    timeout = 300  # 5 minutes
    elapsed = 0
    while not os.path.exists(summary_path) and elapsed < timeout:
        time.sleep(5)
        elapsed += 5

    # Check if summary file exists and process it
    if os.path.exists(summary_path):
        try:
            with open(summary_path, 'r') as f:
                summary = json.load(f)
            summary["execution_time"] = (time.time() - start_time) * 1000  # Add execution time in milliseconds
            logger.info(f"Summary loaded: {summary}")

            # Clean up files
            os.remove(summary_path)
            os.remove(file_path)

            # Render the template with the summary
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "summary": summary,
                    "show_summary": True,
                    "highlight_class": "fraudulent-text",
                    "other_class": "non-fraudulent-text",
                    "highlight_label": "Fraudulent Account Numbers",
                    "other_label": "Non-Fraudulent Account Numbers"
                }
            )
        except Exception as e:
            logger.error(f"Error processing summary file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing summary file: {str(e)}")
    else:
        logger.error(f"DAG execution timed out or failed. Expected file: {summary_path}")
        raise HTTPException(status_code=500, detail="DAG execution timed out or failed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)