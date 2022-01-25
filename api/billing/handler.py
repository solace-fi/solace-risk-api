from api.utils import *
from api.billing.helpers import *

# ----------------------------------------------------
#    REST API HANDLERS
#-----------------------------------------------------

# def post_premium_charged_handler(event, context):
#     try:
#         params = event["body"]
#         verify_chain_id(params=params)
#         verify_account(params=params)
#         verify_charged_amount(params=params)
#         chain_id = params["chain_id"]
#         account = params["account"]
#         charged_amount = params["charged_amount"]

#         unpaid_premium_amount = get_premium_for_account(chain_id, account)
#         premium = unpaid_premium_amount["premium"]
#         if premium != 0 and (premium > charged_amount):
#             return json.dumps({
#                 "status_code": 500,
#                 "result": {"message": f"Unpaid premium amount is bigger than charged premium amount. Unpaid Premium: {premium} Charged Premium: {charged_amount}"}
#             })

#         timestamp = get_timestamp()
#         if "timestamp" in params:
#             timestamp = params["timestamp"]

#         status = post_premium_charged(chain_id=chain_id, account=account, timestamp=timestamp)
#         if status:
#             return response({'chain_id': chain_id, 'account': account, 'premium_charged': status})
#         else:
#             return error_response()

#     except InputException as e:
#         return handle_error(event, e, 400)
#     except Exception as e:
#         return handle_error(event, e, 500)

def get_premium_amount_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        verify_chain_id(params=params)
        verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        result = get_premium_for_account(chain_id=chain_id, account=account)
        if result is not None:
            return response({'chain_id': chain_id, 'account': account, 'premium': result["premium"], 'premium_in_eth': result["premium_in_eth"]})
        else:
            return error_response()

    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def get_paid_billings_by_account_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        verify_chain_id(params=params)
        verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        billings = get_paid_billings_for_account(chain_id=chain_id, account=account)

        if billings is not None:
            return response({'chain_id': chain_id, 'account': account, 'billings': billings})
        else:
            return error_response()
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def get_unpaid_billings_by_account_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        verify_chain_id(params=params)
        verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        billings = get_unpaid_billings_for_account(chain_id=chain_id, account=account)
        if billings is not None:
            return response({'chain_id': chain_id, 'account': account, 'billings': billings})
        else:
            return error_response()
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def get_billings_by_account_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        verify_chain_id(params=params)
        verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        billings = get_billings_by_account(chain_id=chain_id, account=account)
        if billings:
            return response({'chain_id': chain_id, 'account': account, 'billings': billings})
        else:
            return  error_response()
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def get_all_billings_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        verify_chain_id(params=params)

        chain_id = params["chain_id"]
        billings = get_all_billings(chain_id)
        if billings is not None:
            return response({'chain_id': chain_id, 'billings': billings })
        else:
            return error_response()

    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
