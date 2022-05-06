from api.utils import *
import json
import re
from datetime import datetime
from math import floor
import api.balances.get
get_balances = api.balances.get.get_balances

def track():
    least_recent_account = ""
    least_recent_timestamp = 999999999999
    notes = ""
    now = floor(datetime.now().timestamp())
    policies_updated = False
    cfg1 = get_config("1")
    cfg137 = get_config("137")
    # read cache
    try:
        latest_connect = json.loads(s3_get("latest-connect.json"))
    except Exception as e:
        latest_connect = {}
    try:
        policies = json.loads(s3_get("policies-cache.json"))
    except Exception as e:
        policies = {"swcv1":[], "swcv2":[]}
        policies_updated = True
    try:
        positions = json.loads(s3_get("positions-cache.json"))
    except Exception as e:
        positions = {}
    # fill any holes in policy and position caches (including new policies)
    soteriaContracts = {"swcv1": cfg1['soteriaContract'], "swcv2": cfg137['soteriaContract']}
    # loop across all products
    for swcv in ["swcv1", "swcv2"]:
        policy_count = soteriaContracts[swcv].functions.policyCount().call()
        # loop across policies
        for policyID in range(1, policy_count+1):
            # fill holes in policy cache
            query = list(filter(lambda policy: policy['policyID'] == policyID, policies[swcv]))
            if len(query) == 0:
                policies_updated = True
                policyholder = soteriaContracts[swcv].functions.ownerOf(policyID).call()
                policies[swcv].append({'policyID': policyID, 'policyholder': policyholder})
                #sns_publish(f"in risk data zapper cache. new policy detected\nproduct: {swcv}\npolicyID: {policyID}\npolicyholder: {policyholder}")
                #print(f"in risk data zapper cache. new policy detected\nproduct: {swcv}\npolicyID: {policyID}\npolicyholder: {policyholder}")
            else:
                policyholder = query[0]['policyholder']
            # fill holes in position cache
            if policyholder not in positions:
                #print(f"caching {policyholder}")
                get_balances({'account': policyholder, 'chains': [1,137]})
            else:
                pos = positions[policyholder]
                if pos['timestamp'] < least_recent_timestamp:
                    least_recent_account = policyholder
                    least_recent_timestamp = pos['timestamp']
                    notes = f"holds {swcv} policyID {policyID}"
    # also maintain wallets that connected to frontend within last week
    for account in latest_connect:
        pos = positions[account]
        age = now - latest_connect[account]
        if age < 604800 and pos['timestamp'] < least_recent_timestamp:
            least_recent_account = account
            least_recent_timestamp = ts
            notes = "connected to frontend"
    # refresh cache of single policy at a time
    get_balances({'account': least_recent_account, 'chains': [1,137]}, max_cache_age=0)
    #sns_publish(f"in risk data zapper cache. refreshing {least_recent_account}\n{notes}")
    #print(f"in risk data zapper cache. refreshing {least_recent_account}\n{notes}")
    # record policies to cache
    if policies_updated:
        s3_put("policies-cache.json", json.dumps(policies))

# lambda handler
def handler(event, context):
    try:
        track()
        return {
            "statusCode": 200,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
