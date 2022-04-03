from api.utils import *
import json
import re

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
        cfg = get_config("1")
        addr = cfg['w3'].toChecksumAddress(params["account"])
        if not cfg['w3'].isAddress(addr):
            raise InputException(f"Bad request. Invalid address for {params['account']}")
        params["account"] = addr
        networks = get_networks(params['chains'])
        if networks is None:
            raise InputException(f"Bad request. Network names are not found for chains: {params['chains']}")
        params["networks"] = networks
        return params
    except Exception as e:
        raise InputException(f"Error occurred while verifying the params. Error: {e}")

def fetch_positions(params):
    url = f"https://api.zapper.fi/v1/balances-v3?api_key={ZAPPER_API_KEY}&addresses[]={params['account']}"
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

def parse_positions(position_txt, networks):
    try:
        positions = []
        matches = re.findall("event: protocol\ndata: {*.*}", position_txt)
        for match in matches:
            index = match.find('{')
            index2 = match.rfind('}')
            if index == -1 or index2 == -1:
                break
            position = json.loads(match[index:index2+1])
            positions.append(position)
        # order by network, app
        if networks is not None:
            positions = list(filter(lambda position: 'network' in position and position['network'] in networks, positions))
        positions = list(sorted(positions, key = lambda pos: f"{pos['network']} {pos['appId']}"))
        return positions
    except Exception as e:
        raise Exception(f"Error parsing data. Error: {e}")

def clean_positions(positions):
    try:
        results = []
        for position in positions:
            position_info = {}
            # filter out zero balance positions
            if len(position["data"]) == 0:
                continue
            # filter out nfts and tokens
            if position["appId"] == "tokens" or position["appId"] == "nft":
                continue
            # flatten
            balanceUSD = position["meta"]["total"]
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

def get_balances(params):
    params = verify_params(params)
    positions = fetch_positions(params)
    positions = parse_positions(positions, params["networks"])
    positions = clean_positions(positions)
    return json.dumps(positions)

def handler(event, context):
    try:
        response_body = get_balances(json.loads(event["body"]))
        return {
            "statusCode": 200,
            "body": response_body,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
