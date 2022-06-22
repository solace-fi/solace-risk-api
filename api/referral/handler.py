from api.utils import *
import requests

# paths
REFERRAL_CODES_PATH = "/referral-codes"
APPLIED_REFERRAL_CODES_PATH = "/referral-codes/apply"
APPLIED_PROMO_CODES_PATH = "/promo-codes/apply"
REWARDS_INFO = "/rewards-info"

# contants
API_KEY = referral_configs["api_key"]
URL = referral_configs["url"]
contracts = get_swc_contracts()
request_headers = {'x-api-key': API_KEY, 'Content-Type': 'application/json', 'Accept': '*/*'}

    
def get_query_param(event, key):
    param = None
    if event is not None and 'queryStringParameters' in event:
        try:
            param = event['queryStringParameters'][key]
        except:
            pass
    return param

def validate_policy(user: str, chain: str, policy_id: int):
    swc = contracts[chain]
    # check ownership
    p_id = swc["instance"].functions.policyOf(swc["web3"].toChecksumAddress(user)).call()
    if p_id != policy_id:
        return False
    
    # check policy status
    status = swc["instance"].functions.policyStatus(p_id).call()
    if not status:
        return False
    return True

def validata_post_params(body):
    if "user" not in body:
        return InputException("User address must be provided")

    if "chain_id" not in body:
        return InputException("Chain id must be provided")

    if str(body["chain_id"]) not in swc_configs:
        return InputException(f"Chain id {body['chain_id']} is not supported")

    if "policy_id" not in body:
        return InputException(f"Policy id must be provided")
    
    if not validate_policy(body["user"], str(body["chain_id"]), body["policy_id"]):
        return InputException(f"Invalid policy information")

def get_reward_info(user):
    url = f"{URL}info?user={user}" 
    response = requests.get(url, headers=request_headers, timeout=600)
    try:
        response.raise_for_status()
    except:
        raise Exception(response.json())    
    response = response.json()
    return response["result"]["reward_accounting"]

def update_used_rewards(user, used_rewards):
    url = f"{URL}rewards"
    body = {"user": user, "field": "used_rewards", "field_value": used_rewards}
    response = requests.patch(url, headers=request_headers, json=body, timeout=600)
    try:
        response.raise_for_status()
    except:
        raise Exception(response.json()) 
    return response.json()


def handle_info(event):
    user = get_query_param(event, 'user')
    if user is None:
        return InputException("User must be provided")
    url = f"{URL}info?user={user}" 
   
    response = requests.get(url, headers=request_headers, timeout=600)
    try:
        response.raise_for_status()
    except:
        raise Exception(response.json())    
    return response.json()

def handle_apply_promo_code(body):
    validata_post_params(body)
    url = f"{URL}promo-codes/apply"
    
    response = requests.post(url, headers=request_headers, json=body, timeout=600)
    try:
        response.raise_for_status()
    except:
        raise Exception(response.json()) 
    return response.json()

def handle_create_referral_code(body):
    url = f"{URL}referral-codes"
    response = requests.post(url, headers=request_headers, json=body, timeout=600)
   
    print(response.json())
    try:
        response.raise_for_status()
    except:
        raise Exception(response.json())    
    return response.json()

def handle_apply_referral_code(body):
    url = f"{URL}referral-codes/apply"
    response = requests.post(url, headers=request_headers, json=body, timeout=600)
    try:
        response.raise_for_status()
    except:
        raise Exception(response.json())  
    return response.json()

def handler(event, context):
    try:
        method = event['httpMethod']
        path = event['path']
        result = {}
       
        print("Path: ", path)
        # info path
        if method == "GET" and path == REWARDS_INFO:
            result = handle_info(event=event)
        # apply promo code
        elif method == "POST" and path == APPLIED_PROMO_CODES_PATH:
            request_body = json.loads(event['body'])
            result = handle_apply_promo_code(request_body)
        elif method == "POST" and path == REFERRAL_CODES_PATH:
            request_body = json.loads(event['body'])
            result =  handle_create_referral_code(request_body)
        elif method == "POST" and path == APPLIED_REFERRAL_CODES_PATH:
            request_body = json.loads(event['body'])
            result = handle_apply_referral_code(request_body)
        else:
            result = {"message": "No operation found"}

        return {
            "statusCode": 200,
            "body": json.dumps(result),
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
