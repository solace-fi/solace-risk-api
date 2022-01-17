from api.tracks import track_policy_rates
from api.utils import *

import asyncio

def handler(event, context):
    try:
        asyncio.run(track_policy_rates())
        return {
            "statusCode": 200,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)