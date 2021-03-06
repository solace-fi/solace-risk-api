from api.utils import *

# ----------------------------------------------------
#    HELPER FUNCTIONS
#-----------------------------------------------------

def save_premiums_charged(chain: str, accounts: list):
    try:
        timestamp = get_timestamp()
        billings = get_swc_billing_data_from_s3(chain)
        for account in accounts:
            if account not in billings:
                continue
            for billing_by_account in billings[account]:
                if billing_by_account["charged"] == False:
                    billing_by_account["charged"] = True
                    billing_by_account["charged_time"] = timestamp
        save_billings_data_to_s3(chain, billings)
        return True
    except Exception as e:
        handle_error({"resource": "billing.helpers.save_premiums_charged()"}, e, 500)
        return False

def post_premium_charged(chain_id: str, account: str, timestamp: str):
    try:
        billings = get_swc_billing_data_from_s3(chain_id)
        for billing_by_account in billings[account]:
            if billing_by_account["charged"] == False:
                billing_by_account["charged"] = True
                billing_by_account["charged_time"] = timestamp
        save_billings_data_to_s3(chain_id, billings)
        return True
    except Exception as e:
        handle_error({"resource": "billing.helpers.post_premium_charged()"}, e, 500)
        return False

def get_all_billings(chain_id: str):
    try:
        billings = get_swc_billing_data_from_s3(chain_id)
        result = []
        for account, account_billings in billings.items():
            for account_billing in account_billings:
                account_billing["address"] = account
                result.append(account_billing)
        return result
    except Exception as e:
        handle_error({"resource": "billing.helpers.get_all_billings()"}, e, 500)
        return None

def get_billings_by_account(chain_id: str, account: str):
    try:
        billings = get_billings_by_account(chain_id, account)
        return billings
    except Exception as e:
        handle_error({"resource": "billing.helpers.get_billings_by_account()"}, e, 500)
        return None

def get_unpaid_billings_for_account(chain_id: str, account: str):
    try:
        billings = get_billings_by_account(chain_id, account)
        billings = list(filter(lambda billing: billing["charged"] == False, billings))
        return billings
    except Exception as e:
        handle_error({"resource": "billing.helpers.get_unpaid_billings_for_account()"}, e, 500)
        return None

def get_unpaid_billings(chain_id: str):
    try:
        billings = get_billings(chain_id)
        unpaid_billings = []
        for account, account_billings in billings.items():
            unpaid_billings.append( {"account": account, "billings": list(filter(lambda billing: billing["charged"] == False and billing["premium"] > 0, account_billings )) })
        return unpaid_billings
    except Exception as e:
        handle_error({"resource": "billing.helpers.get_unpaid_billings()"}, e, 500)
        return None

def get_unpaid_premiums(chain_id: str, swc_versions: list):
    try:
        billings = get_billings(chain_id)
        unpaid_billings = []
        for account, account_billings in billings.items():
            unpaid_billings.append( {"account": account, "billings": list(filter(lambda billing: billing["charged"] == False and billing["premium"] > 0 and billing["swc_version"] in swc_versions, account_billings )) })

        premiums = []
        for billing_info in unpaid_billings:
            premium = 0
            for account_billing in billing_info["billings"]:
                premium = premium + account_billing["premium"]
            
            if premium > 0:
                premiums.append({"account": billing_info["account"], "premium": premium})
        return premiums
    except Exception as e:
        handle_error({"resource": "billing.helpers.get_unpaid_premiums()"}, e, 500)
        return None

def get_paid_billings_for_account(chain_id: str, account: str):
    try:
        billings = get_billings_by_account(chain_id, account)
        billings = list(filter(lambda billing: billing["charged"] == True, billings))
        return billings
    except Exception as e:
        handle_error({"resource": "billing.helpers.get_paid_billings_for_account()"}, e, 500)
        return None

def get_premium_for_account(chain_id: str, account: str):
    try:
        billings = get_unpaid_billings_for_account(chain_id, account)
        result = {}
        premium = 0
        for billing in billings:
            premium = premium + billing["premium"]
        result["premium"] = premium
        return result
    except Exception as e:
        handle_error({"resource": "billing.helpers.get_premium_for_account()"}, e, 500)
        return None

def get_soteria_premiums(chain_id: str):
    try:
        unpaid_billings = get_unpaid_billings(chain_id)
        premiums = []
        for unpaid_billing in unpaid_billings:
            premium = 0
            for billing in unpaid_billing["billings"]:
                premium = premium + billing["premium"]
            premiums.append({"account": unpaid_billing["account"], "premium": premium})
        return premiums
    except Exception as e:
        handle_error({"resource": "billing.helpers.get_premium_amounts()"}, e, 500)

def verify_chain_id(params):
    if "chain_id" not in params:
        raise InputException("Chain id must be provided")

    chain_id = params["chain_id"]
    if int(chain_id) not in get_supported_chains():
        raise InputException(f"Chain Id: {chain_id} is not supported yet")

def verify_account(params):
    if "account" not in params:
        raise InputException("Account address must be provided")

def verify_charged_amount(params):
    if "charged_amount" not in params:
        raise InputException("Premium charged amount must be provided")

def get_billings(chain_id: str):
    billings = get_swc_billing_data_from_s3(chain_id=chain_id)
    return billings

def get_billings_by_account(chain_id: str, account: str):
    billings = get_swc_billing_data_from_s3(chain_id)
    if account in billings:
        return billings[account]
    return []

def error_response():
    return {
        "statusCode": 500,
        "body": {"message": "Something went wrong"},
        "headers": headers
    }

def response(result):
    return {
        "statusCode": 200,
        "body": json.dumps(result),
        "headers": headers
    }
