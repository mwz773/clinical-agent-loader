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
    dbname=os.environ["DB_NAME"],
    user=secret["username"],
    password=secret["password"],
    sslmode="require",
)

with connection, connection.cursor() as cursor:
    cursor.execute(
        """
        SELECT patient_id, full_name, birth_date, gender
        FROM patients
        ORDER BY patient_id
        LIMIT 20
    """
)

    for patient_id, full_name, birth_date, gender in cursor.fetchall():
        print(
            f"Name: {full_name} | "
            f"Patient ID: {patient_id} | "
            f"Birth date: {birth_date} | "
            f"Gender: {gender}"
        )

    for patient in cursor.fetchall():
        print(patient)

connection.close()