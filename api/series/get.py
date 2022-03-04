from api.utils import *
import json

def handler(event, context):
    try:
        response_body = s3_get("current-rate-data/series.json")
        return {
            "statusCode": 200,
            "body": response_body,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
