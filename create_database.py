import json
import os

import boto3
import psycopg2

DATABASE_NAME = "clinical_agent"

secret = json.loads(
    boto3.client(
        "secretsmanager",
        region_name=os.environ["AWS_REGION"],
    ).get_secret_value(
        SecretId=os.environ["DB_SECRET_ARN"]
    )["SecretString"]
)

connection = psycopg2.connect(
    host=os.environ["DB_HOST"],
    port=os.environ.get("DB_PORT", "5432"),
    dbname="postgres",
    user=secret["username"],
    password=secret["password"],
    sslmode="require",
    connect_timeout=10,
)

connection.autocommit = True

with connection.cursor() as cursor:
    cursor.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s",
        (DATABASE_NAME,),
    )

    if cursor.fetchone():
        print(f"Database already exists: {DATABASE_NAME}")
    else:
        cursor.execute(f"CREATE DATABASE {DATABASE_NAME}")
        print(f"Created database: {DATABASE_NAME}")

connection.close()