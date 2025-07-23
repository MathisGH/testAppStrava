import os
import pandas as pd
import psycopg2 # Database connector library to connect to a PostgreSQL database instance from our python script
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

def connect_to_db(): # Function to connect to the PostgreSQL database
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", 5432),
    )

def create_table():
    connector = connect_to_db() # We first start by connecting to the database
    cursor = connector.cursor() # Then we create a cursor that will execute SQL commands
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS athlete_stats (
                id SERIAL PRIMARY KEY,
                athlete_id TEXT,
                date DATE,
                distance_km FLOAT,
                duration_min FLOAT,
                average_speed FLOAT,
                elevation_gain FLOAT
            );
        """)
    connector.commit()
    cursor.close()
    connector.close()

def insert_dataframe(df: pd.DataFrame, connector):
    cursor = connector.cursor()
    try:
        for _, row in df.iterrows(): # The '%s' are placeholders for the values to be inserted (avoid SQL injection)
            cursor.execute("""
                INSERT INTO athlete_stats (athlete_id, date, distance_km, duration_min, average_speed, elevation_gain)
                VALUES (%s, %s, %s, %s, %s, %s); 
            """, (
                row["athlete_id"],
                row["start_date"],
                row["distance_km"],
                row["duration_min"],
                row["average_speed"],
                row["elevation_gain"]
            ))
        connector.commit()
    finally: # Allow the cursor and connection to be closed even if an error occurs
        cursor.close()
        connector.close()