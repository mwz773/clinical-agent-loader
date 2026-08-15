import json
import os

import boto3
import psycopg2

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
    dbname=os.environ.get("DB_NAME", "clinical_agent"),
    user=secret["username"],
    password=secret["password"],
    sslmode="require",
    connect_timeout=10,
)

with connection, connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_user, version();")
    database, user, version = cursor.fetchone()

print(f"Connected to database: {database}")
print(f"Connected as database user: {user}")
print(f"PostgreSQL version: {version.split(',')[0]}")

connection.close()