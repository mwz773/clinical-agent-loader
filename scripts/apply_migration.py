"""Apply one SQL migration to the clinical-agent PostgreSQL database."""

import argparse
import json
import os
from pathlib import Path

import boto3
import psycopg2


def get_connection():
    secret = json.loads(
        boto3.client(
            "secretsmanager", region_name=os.environ["AWS_REGION"]
        ).get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    )
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "clinical_agent"),
        user=secret["username"],
        password=secret["password"],
        sslmode="require",
    )


def main():
    parser = argparse.ArgumentParser(description="Apply one PostgreSQL migration file.")
    parser.add_argument("migration", type=Path, help="Path to a .sql migration file.")
    args = parser.parse_args()

    if args.migration.suffix != ".sql" or not args.migration.is_file():
        parser.error("migration must be an existing .sql file")

    sql = args.migration.read_text(encoding="utf-8")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)

    print(f"Applied migration: {args.migration}")


if __name__ == "__main__":
    main()
