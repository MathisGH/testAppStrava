# Athlete Performance Analysis — Strava Data

Endurance sports data analysis project based on Strava activities.
The project focuses on data collection, cleaning, feature engineering and exploratory training analysis.

⚠ Not affiliated with Strava.  
Activities are accessed via the official Strava API and link back to Strava:
https://www.strava.com/activities/{activity_id}

---

## Project overview

This project was built as a personal data science project to explore sports data and find insights related to training performance.
The goal was also to practice machine learning, with a focus on unsupervised methods (clustering), due to limited data quality and volume.

The emphasis is on:
- building a reproducible data pipeline
- handling noisy and incomplete data
- engineering meaningful training and performance indicators

---

## Application

A simple Streamlit application (hosted with AWS) is used to authenticate athletes via Strava OAuth and trigger data collection.

Test URL (may be offline if AWS subscription is over):
http://35.180.120.114:8501/

---

## Tech stack

- Python
- Pandas / NumPy
- Scikit-learn
- Streamlit
- Strava API
- AWS (EC2)

---

## Data pipeline

1. Athlete authentication via Strava OAuth
2. Raw activity collection from the Strava API
3. Data cleaning and normalization
4. Feature engineering (training load, intensity, heart rate zones, speed variability...)
5. Aggregation at activity and athlete levels

---

## Main datasets (processed)

- **activities_master**  
  Activity-level dataset enriched with engineered features used for analysis.

- **activity_splits**  
  Split-level data used to compute variability and heart rate zone distributions.

- **best_efforts**  
  Extracted personal best performances across standard distances.

- **athletes_summary**  
  Aggregated athlete-level statistics and performance indicators.

---

## Limitations

- Limited number of athletes
- Variable data quality depending on devices and recording habits

---

## Disclaimer

This project is for educational and exploratory purposes only.
