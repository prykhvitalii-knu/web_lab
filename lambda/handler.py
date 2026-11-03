import json
import os

import boto3
from mangum import Mangum

_adapter = None


def handler(event, context):
    global _adapter
    if _adapter is None:
        secret = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["APP_SECRETS_ARN"]
        )
        os.environ.update(json.loads(secret["SecretString"]))
        from app.main import app

        _adapter = Mangum(app)
    return _adapter(event, context)
