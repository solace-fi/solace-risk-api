from api.utils import *

def risk_function():
    return json.dumps({
        "results": "go here"
    })

def handler(event, context):
    try:
        body = risk_function()
        return {
            "statusCode": 200,
            "body": body,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
