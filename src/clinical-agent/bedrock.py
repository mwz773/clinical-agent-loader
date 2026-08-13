import os

import boto3
from botocore.exceptions import ClientError

model_id = os.environ["BEDROCK_MODEL_ID"]

client = boto3.client(
    "bedrock-runtime",
    region_name=os.environ["AWS_REGION"],
)

try:
    response = client.converse(
        modelId=model_id,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": (
                            "Reply with exactly: "
                            "Bedrock connection successful."
                        )
                    }
                ],
            }
        ],
        inferenceConfig={
            "maxTokens": 30,
            "temperature": 0,
        },
    )

    print(response["output"]["message"]["content"][0]["text"])

except ClientError as error:
    print(f"Bedrock test failed: {error}")
    raise