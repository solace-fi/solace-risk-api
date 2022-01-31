from api.utils import *
from datetime import datetime
import pandas as pd
import numpy as np
import json
import math


def handler(event, context):
    try:
        print("body:")
        print(event["body"])
        res = event["body"]
        return {
            "statusCode": 200,
            "body": res,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
