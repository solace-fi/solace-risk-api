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
def fetch_from_zapper(params):
    zapper_response = call_to_zapper(params)
    zapper_events = parse_zapper_response(zapper_response)
    positions_cleaned = parse_zapper_events(zapper_events)
    cache_positions(zapper_events, positions_cleaned, params['account'])
    return positions_cleaned

# makes the http call to zapper api
def call_to_zapper(params):
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
def parse_zapper_response(position_txt):
    try:
        zapper_events = []
        matches = re.findall("event: \S+\ndata: {.*}", position_txt)
        for match in matches:
            # parse body
            iL = match.find('{')
            iR = match.rfind('}')
            if iL == -1 or iR == -1:
                break
            data = json.loads(match[iL:iR+1])
            # find event name
            jR = match.find('\n')
            event = match[0:jR]
            zapper_events.append({
                "event": event,
                "data": data
            })
        return zapper_events
    except Exception as e:
        raise Exception(f"Error parsing data. Error: {e}")

# removes unnecessary info
def parse_zapper_events(zapper_events):
    # TODO: what about the other event types?
    accepted_events = list(filter(lambda event: event['event'] == 'event: balance', zapper_events))
    positions = list(map(lambda event: event['data'], accepted_events))
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
        results = sorted(results, key=lambda event: -event['balanceUSD'])
        return results
    except Exception as e:
        raise Exception(f"error cleaning positions data. Error {e}")

# writes the positions to cache
def cache_positions(zapper_events, positions_cleaned, account):
    # write positions to cache
    record = {
        "timestamp": floor(datetime.now().timestamp()),
        "zapper_events": zapper_events,
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

# fetches positions from the s3 cache
# throws on not cached or not cached recently enough
def fetch_from_s3(params, max_cache_age=86400):
    cache = json.loads(s3_get(f"positions-cache/{params['account']}.json"))
    age = floor(datetime.now().timestamp()) - cache['timestamp']
    if age > max_cache_age:
        raise Exception("cache too old")
    positions_cleaned = cache['positions_cleaned']
    return positions_cleaned

# returns the balances of an account
# attempts to read from cache before reading from zapper
def get_balances(params, max_cache_age=86400):
    params = verify_params(params)
    try:
        positions_cleaned = fetch_from_s3(params, max_cache_age)
    except Exception as e:
        positions_cleaned = fetch_from_zapper(params)
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
