import json
import os
from pathlib import Path

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
    dbname=os.environ["DB_NAME"],
    user=secret["username"],
    password=secret["password"],
    sslmode="require",
    connect_timeout=10,
)

sql = Path("schema.sql").read_text(encoding="utf-8")

with connection:
    with connection.cursor() as cursor:
        cursor.execute(sql)

connection.close()
print("Schema applied successfully.")