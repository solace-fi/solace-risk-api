from api.utils import *
from api.billing.swc_billing_calculator import calculate_single_bill
from api.cancel.premium_data_signer import sign

def sign_premium_data(params):
    if "chain_id" not in params:
        raise InputException("Chain id should be provided")
    chain = params["chain_id"]

    if "policyholder" not in params:
        raise InputException("Policyholder should be provided")
    policyholder = params["policyholder"]

    premium = calculate_single_bill(chain, policyholder)
    result = sign(premium, policyholder, chain)
    return result

def handler(event, context):
    try:
        params = event["queryStringParameters"]
        if params is None:
            result = {}
        else:
            result = sign_premium_data(params)

        return {
            "statusCode": 200,
            "body": json.dumps(result),
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
