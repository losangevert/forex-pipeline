# webserver_config.py — Configuration de l'interface Web Airflow
import os

SECRET_KEY = os.environ.get("AIRFLOW__WEBSERVER__SECRET_KEY", "forex_pipeline_secret_key_2026")

# Authentification locale (base de données Airflow)
AUTH_TYPE = 1
AUTH_ROLE_ADMIN = "Admin"
AUTH_ROLE_PUBLIC = "Admin"
