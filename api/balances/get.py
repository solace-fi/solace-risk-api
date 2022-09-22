from api.utils import *
from itertools import groupby
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
    positions_cleaned = parse_zapper_events(zapper_events, params)
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
def parse_zapper_events(zapper_events, params):
    # TODO: what about the other event types?
    try:
        results = []
        has_stakedao_app = False
        for event in zapper_events:
            if event['event'] != 'event: balance' or event['data']['appId'] == "nft" or event['data']['appId'] == "tokens":
                continue

            for position in event['data']['app']['data']:
                position_info = {}
                balanceUSD = position["balanceUSD"]
                if balanceUSD == 0:
                    continue

                # don't change the order
                position_info["appId"] = position["appId"]
                position_info["network"] = position["network"]
                position_info["balanceUSD"] = balanceUSD
                if position['appId'] == 'stake-dao':
                    has_stakedao_app = True
                    position_info["balanceUSD"] += add_app_balance('stake-dao', position['network'])
                results.append(position_info)

        # PATCH: StakeDAO Liquid Locker Positions
        if not has_stakedao_app:
            results += add_stake_dao_lock_positions(params['account'])
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

    def key_func(k):
        return k['appId'], k['network']
    filtered_positions = []
    for key, value in groupby(positions, key_func):
        balanceUSD = sum(list(map(lambda position: position["balanceUSD"], value)))
        filtered_positions.append({"appId": key[0], "network": key[1], "balanceUSD": balanceUSD})
    return filtered_positions

# fetches positions from the s3 cache
# throws on not cached or not cached recently enough
def fetch_from_s3(params, max_cache_age=86400):
    cache = json.loads(s3_get(f"positions-cache/{params['account']}.json"))
    age = floor(datetime.now().timestamp()) - cache['timestamp']
    if age > max_cache_age:
        raise Exception("cache too old")
    positions_cleaned = cache['positions_cleaned']
    return positions_cleaned

def add_app_balance(appId, network, account):
    try:
        response = requests.get(f"https://api.zapper.fi/v2/apps/{appId}/balances?api_key={ZAPPER_API_KEY}&addresses[]={account}&network={network}")
        products = response.json()['balances'][account]['products']

        balance_usd = 0
        for product in products:
            for asset in product['assets']:
                if asset['type'] == 'contract-position':
                    if asset['balanceUSD'] == 0:
                        continue
                    balance_usd += asset['balanceUSD']

        return balance_usd
    except:
        return []

def add_stake_dao_lock_positions(account):
    try:
        response = requests.get(f"https://api.zapper.fi/v2/apps/stake-dao/balances?api_key={ZAPPER_API_KEY}&addresses[]={account}")
        products = response.json()['balances'][account]['products']

        position_balance_by_network = {}
        for product in products:
            for asset in product['assets']:
                if asset['type'] == 'contract-position':
                    if asset['balanceUSD'] == 0:
                        continue
                    if asset['network'] not in position_balance_by_network:
                        position_balance_by_network[asset['network']] = 0
                    position_balance_by_network[asset['network']] = position_balance_by_network[asset['network']] + asset['balanceUSD']

        positions = []
        for k, v in position_balance_by_network.items():
            positions.append({'appId': 'stake-dao', 'network': k, 'balanceUSD': v})
        return positions
    except:
        return []

# returns the balances of an account
# attempts to read from cache before reading from zapper
def get_balances(params, max_cache_age=86400):
    params = verify_params(params)
    try:
        positions_cleaned = fetch_from_s3(params, max_cache_age)
        if len(positions_cleaned) == 0:
            positions_cleaned = fetch_from_zapper(params)
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

