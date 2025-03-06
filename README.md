# Mlops_pipeline
![image](https://github.com/user-attachments/assets/792e95f4-b869-4996-bcaa-987014053454)

fraud detection model 

ML Pipeline 


Data Ingestion and Storage in S3 or local storage


○	Description: Covers the process of collecting bank statements from sources (Perfios, OneMoney, FinBox, ScoreMe) and storing them in Amazon S3 for scalable, durable storage.


        Workflow Orchestration with Airflow
        
○	Description: Explains how Airflow schedules and orchestrates the processing of S3 files, triggering the ML pipeline for each new statement.


     Feature Extraction and Engineering

 
○	Description: Details the extraction of raw data from bank statements, engineering features (e.g., transaction amounts, dates, IsWeekend, AmountAbs), and preparing them for ML.

        Feature Management with Feast
        
○	Description: Describes how Feast stores and manages features in its online store, enabling real-time access for ML models and ensuring feature consistency.


     ML Model Loading and Prediction

     
○	Description: Focuses on loading pre-trained ML models and scalers from pickle files, processing features from Feast, and generating fraud predictions (probabilities and classifications).

    

    Summary Generation

    
○	Description: Covers the creation of a summary (e.g., total transactions, fraudulent transactions, account-level fraud percentages).


    Results Display via FastAPI

    
○	Description: Explains how FastAPI retrieves the summary from temporary storage, renders it in an HTML dashboard, and presents fraud detection results to users.


Execution :
1)	   python3 -m venv venv
	   source venv/bin/activate
2)	   pip install -r req.txt 
3)	   airflow db init
       airflow webserver --port 8080 &
       airflow scheduler &
4)	   cd fraud_detection_pipeline/feature_store
        feast apply.
        Run main.py
5)	    uvicorn main:app --host 0.0.0.0 --port 7900

