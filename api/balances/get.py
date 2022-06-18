from api.utils import *
import json
import re
from datetime import datetime
from math import floor

# verify the parameters
def verify_params(params):
    if params is None:
        raise InputException("missing params")
    if "account" not in params:
        raise InputException("missing account address")
    if 'chains' not in params:
        if 'chain_id' in params:
            params["chains"] = [int(params['chain_id'])]
        else:
            raise InputException(f"Bad request. Chain info is not provided")
    try:
        networks = get_networks(params['chains'])
        if networks is None:
            raise InputException(f"Bad request. Network names are not found for chains: {params['chains']}")
        params["networks"] = networks
        return params
    except Exception as e:
        raise InputException(f"Error occurred while verifying the params. Error: {e}")

# fetches the positions of an account from zapper
def fetch_positions(params):
    url = f"https://api.zapper.fi/v2/balances?api_key={ZAPPER_API_KEY}&addresses[]={params['account']}&useNewBalancesFormat=true"
    for i in range(1):
        try:
            response = requests.get(url, timeout=600)
            response.raise_for_status()
            return response.text
        except Exception as e:
            msg = f"In Solace Risk API get balances. Error fetching data from zapper\nURL   : {url}\nIP    : {get_IP_address()}\nError : {e}"
            print(msg)
            sns_publish(msg)
    raise Exception("error fetching data")

# parses the zapper response object
def parse_positions(position_txt):
    try:
        positions = []
        matches = re.findall("event: balance\ndata: {*.*}", position_txt)
        for match in matches:
            index = match.find('{')
            index2 = match.rfind('}')
            if index == -1 or index2 == -1:
                break
            position = json.loads(match[index:index2+1])
            # filter out nfts and tokens
            if position["appId"] == "tokens" or position["appId"] == "nft":
                continue

            positions.append(position)
        return positions
    except Exception as e:
        raise Exception(f"Error parsing data. Error: {e}")

# removes unnecessary info
def clean_positions(positions):
    try:
        results = []
        for position in positions:
            position_info = {}
            # filter out zero balance positions
            if len(position["data"]) == 0:
                continue
           
            # flatten
            balanceUSD = position["balanceUSD"]
            if balanceUSD == 0:
                 continue
            # don't change the order
            position_info["appId"] = position["appId"]
            position_info["network"] = position["network"]
            position_info["balanceUSD"] = balanceUSD
            results.append(position_info)
        return results
    except Exception as e:
        raise Exception(f"error cleaning positions data. Error {e}")

# writes the positions to cache
def cache_positions(positions_parsed, positions_cleaned, account):
    # write positions to cache
    record = {
        "timestamp": floor(datetime.now().timestamp()),
        "positions_parsed": positions_parsed,
        "positions_cleaned": positions_cleaned
    }
    s3_put(f"positions-cache/{account}.json", json.dumps(record))
    try:
        cache = json.loads(s3_get("positions-cache.json"))
    except Exception as e:
        cache = {}
    cache[account] = record
    s3_put("positions-cache.json", json.dumps(cache))

# removes positions that are not on one of the requested networks
def filter_positions(positions, networks):
    # order by network, app
    if networks is not None:
        positions = list(filter(lambda position: 'network' in position and position['network'] in networks, positions))
    positions = list(sorted(positions, key = lambda pos: f"{pos['network']} {pos['appId']}"))
    return positions

# returns the balances of an account
# attempts to read from cache before reading from zapper
def get_balances(params, max_cache_age=86400):
    #print(f"fetching balances of {json.dumps(params)}")
    params = verify_params(params)
    try:
        #print("attempting to read from cache")
        cache = json.loads(s3_get(f"positions-cache/{params['account']}.json"))
        age = floor(datetime.now().timestamp()) - cache['timestamp']
        if age > max_cache_age:
            raise Exception("cache too old")
        #positions_parsed = cache['positions_parsed']
        positions_cleaned = cache['positions_cleaned']
    except Exception as e:
        #print("fetching from zapper")
        positions_raw = fetch_positions(params)
        positions_parsed = parse_positions(positions_raw)
        positions_cleaned = clean_positions(positions_parsed)
        cache_positions(positions_parsed, positions_cleaned, params['account'])
    positions_filtered = filter_positions(positions_cleaned, params["networks"])
    return json.dumps(positions_filtered)

# records that a lookup was made on an accounts balances
# roughly equivalent to saying a wallet connected to the frontend
# wallets that connected recently will be maintained in cache
def record_connect(params):
    params = verify_params(params)
    account = params['account']
    filename = "latest-connect.json"
    try:
        latest_connect = json.loads(s3_get(filename))
    except Exception as e:
        latest_connect = {}
    latest_connect[account] = floor(datetime.now().timestamp())
    s3_put(filename, json.dumps(latest_connect))

# lambda handler
def handler(event, context):
    try:
        response_body = get_balances(json.loads(event["body"]))
        record_connect(json.loads(event["body"]))
        return {
            "statusCode": 200,
            "body": response_body,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
