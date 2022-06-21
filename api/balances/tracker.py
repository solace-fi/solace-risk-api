from api.utils import *
import json
import re
from datetime import datetime
from math import floor
import api.balances.get
get_balances = api.balances.get.get_balances

# trick to use the previous caches
SWC_MAPPER = {
    '1': "swcv1",
    '137': "swcv2",
    '205': "swcv3",
    '1313161554': "swcv4"
}

def track():
    least_recent_account = ""
    least_recent_timestamp = 999999999999
    notes = ""
    now = floor(datetime.now().timestamp())
    policies_updated = False
    policyholders = set()
    supported_chains = get_supported_chains()

    # read cache
    try:
        latest_connect = json.loads(s3_get("latest-connect.json"))
    except Exception as e:
        latest_connect = {}
    try:
        policies = json.loads(s3_get("policies-cache.json"))
    except Exception as e:
        policies = {"swcv1":[], "swcv2":[], "swcv3":[], "swcv4":[]}
        policies_updated = True
    try:
        positions = json.loads(s3_get("positions-cache.json"))
    except Exception as e:
        positions = {}
    # fill any holes in policy and position caches (including new policies)
    swc_contracts = get_swc_contracts()
    # loop across all products
    for chain, swc in swc_contracts.items():
        policy_count = swc["instance"].functions.policyCount().call()

        # TODO: this is a TRICK to use previous swcv1 and swcv2  mapped caches
        if chain not in SWC_MAPPER:
            continue
        swc_version = SWC_MAPPER[chain]

        # loop across policies
        for policyID in range(1, policy_count+1):
            # fill holes in policy cache
            query = list(filter(lambda policy: policy['policyID'] == policyID, policies[swc_version]))
            if len(query) == 0:
                policies_updated = True
                policyholder = swc["instance"].functions.ownerOf(policyID).call()
                policies[swc_version].append({'policyID': policyID, 'policyholder': policyholder})
                policyholders.add(policyholder)
                #sns_publish(f"in risk data zapper cache. new policy detected\nproduct: {swcv}\npolicyID: {policyID}\npolicyholder: {policyholder}")
                #print(f"in risk data zapper cache. new policy detected\nproduct: {swcv}\npolicyID: {policyID}\npolicyholder: {policyholder}")
            else:
                policyholder = query[0]['policyholder']
            # fill holes in position cache
            if policyholder not in positions:
                #print(f"caching {policyholder}")
                get_balances({'account': policyholder, 'chains': supported_chains})
            else:
                pos = positions[policyholder]
                if pos['timestamp'] < least_recent_timestamp:
                    least_recent_account = policyholder
                    least_recent_timestamp = pos['timestamp']
                    notes = f"holds {swc_version} policyID {policyID}"
    # also maintain wallets that connected to frontend within last week
    for account in latest_connect:
        if account in policyholders:
            continue
        if account in positions:
            pos = positions[account]
            age = now - latest_connect[account]
            if age < 604800 and pos['timestamp'] < least_recent_timestamp:
                least_recent_account = account
                least_recent_timestamp =  pos['timestamp']
                notes = "connected to frontend"
    # refresh cache of single policy at a time
    get_balances({'account': least_recent_account, 'chains': supported_chains}, max_cache_age=0)
    #sns_publish(f"in risk data zapper cache. refreshing {least_recent_account}\n{notes}")
    print(f"in risk data zapper cache. refreshing {least_recent_account}\n{notes}")
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
