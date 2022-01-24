from api.utils import *

# ----------------------------------------------------
#    REST API HANDLERS
#-----------------------------------------------------

def post_premium_charged_handler(event, context):
    try:
        params = event["body"]
        __verify_chain_id(params=params)
        __verify_account(params=params)
        __verify_charged_amount(params=params)
        chain_id = params["chain_id"]
        account = params["account"]
        charged_amount = params["charged_amount"]

        unpaid_premium_amount = get_premium_for_account(chain_id, account)
        premium = unpaid_premium_amount["premium"]
        if premium != 0 and (premium > charged_amount):
            return json.dumps({
                "status_code": 500,
                "result": {"message": f"Unpaid premium amount is bigger than charged premium amount. Unpaid Premium: {premium} Charged Premium: {charged_amount}"}
            })

        timestamp = get_timestamp()
        if "timestamp" in params:
            timestamp = params["timestamp"]

        status = post_premium_charged(chain_id=chain_id, account=account, timestamp=timestamp)
        if status:
            return __response({'chain_id': chain_id, 'account': account, 'premium_charged': status})
        else:
            return __error_response()

    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def get_premium_amount_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        __verify_chain_id(params=params)
        __verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        result = get_premium_for_account(chain_id=chain_id, account=account)
        if result is not None:
            return __response({'chain_id': chain_id, 'account': account, 'premium': result["premium"], 'premium_in_eth': result["premium_in_eth"]})
        else:
            return __error_response()

    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def get_paid_billings_by_account_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        __verify_chain_id(params=params)
        __verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        billings = get_paid_billings_for_account(chain_id=chain_id, account=account)

        if billings is not None:
            return __response({'chain_id': chain_id, 'account': account, 'billings': billings})
        else:
            return __error_response()
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def get_unpaid_billings_by_account_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        __verify_chain_id(params=params)
        __verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        billings = get_unpaid_billings_for_account(chain_id=chain_id, account=account)
        if billings is not None:
            return __response({'chain_id': chain_id, 'account': account, 'billings': billings})
        else:
            return __error_response()
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def get_billings_by_account_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        __verify_chain_id(params=params)
        __verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        billings = get_billings_by_account(chain_id=chain_id, account=account)
        if billings:
            return __response({'chain_id': chain_id, 'account': account, 'billings': billings})
        else:
            return  __error_response()
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def get_all_billings_handler(event, context):
    try:
        params = event["queryStringParamaters"]
        __verify_chain_id(params=params)

        chain_id = params["chain_id"]
        billings = get_all_billings(chain_id)
        if billings is not None:
            return __response({'chain_id': chain_id, 'billings': billings })
        else:
            return __error_response()

    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

# ----------------------------------------------------
#    HANDLER FUNCTIONS
#-----------------------------------------------------

def post_premium_charged(chain_id: str, account: str, timestamp: str):
    try:
        billings = get_billings(chain_id)
        for billing_by_account in billings[chain_id][account]:
            if billing_by_account["charged"] == False:
                billing_by_account["charged"] = True
                billing_by_account["charged_time"] = timestamp
        save_billings(chain_id, billings)
        return True
    except Exception as e:
        handle_error(e)
        return False

def get_all_billings(chain_id: str):
    try:
        billings = __get_billings(chain_id)
        result = []
        for account, account_billings in billings.items():
            for account_billing in account_billings:
                account_billing["address"] = account
                result.append(account_billing)
        return result
    except Exception as e:
        handle_error(e)
        return None

def get_billings_by_account(chain_id: str, account: str):
    try:
        billings = __get_billings_by_account(chain_id, account)
        return billings
    except Exception as e:
        handle_error(e)
        return None

def get_unpaid_billings_for_account(chain_id: str, account: str):
    try:
        billings = __get_billings_by_account(chain_id, account)
        billings = list(filter(lambda billing: billing["charged"] == False, billings))
        return billings
    except Exception as e:
        handle_error(e)
        return None

def get_paid_billings_for_account(chain_id: str, account: str):
    try:
        billings = __get_billings_by_account(chain_id, account)
        billings = list(filter(lambda billing: billing["charged"] == True, billings))
        return billings
    except Exception as e:
        handle_error(e)
        return None

def get_premium_for_account(chain_id: str, account: str):
    try:
        billings = get_unpaid_billings_for_account(chain_id, account)
        result = {}
        premium = 0
        for billing in billings:
            premium = premium + billing["premium"]
        premium_in_eth = get_price_in_eth(premium)
        result["premium"] = premium
        result["premium_in_eth"] = premium_in_eth
        return result
    except Exception as e:
        handle_error(e)
        return None

# ----------------------------------------------------
#    HELPER FUNCTIONS
#-----------------------------------------------------

def __verify_chain_id(params):
    if "chain_id" not in params:
        raise InputException("Chain id must be provided")

    chain_id = params["chain_id"]
    if chain_id not in get_supported_chains():
        raise InputException(f"Chain Id: {chain_id} is not supported yet")

def __verify_account(params):
    if "account" not in params:
        raise InputException("Account address must be provided")

def __verify_charged_amount(params):
    if "charged_amount" not in params:
        raise InputException("Premium charged amount must be provided")

def __get_billings(chain_id: str):
    billings = get_billings(chain_id=chain_id)
    billings = billings[chain_id]
    return billings

def __get_billings_by_account(chain_id: str, account: str):
    billings = __get_billings(chain_id)
    return billings[account]

def __error_response():
    return json.dumps({
        "status_code": 500,
        "result": {"message": "Something went wrong"}
    })

def __response(result):
    return json.dumps({
        "status_code": 200,
        "result": result
    })
    