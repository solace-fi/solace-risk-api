from api.utils import *

def verify_account(params):
    if "account" not in params:
        raise InputException("missing account") # check policy id exists
    try:
        addr = w3.toChecksumAddress(params["account"])
        if not w3.isAddress(addr):
            raise "invalid address"
        return addr
    except Exception as e:
        raise InputException(f"invalid account: '{params['account']}'") # check policy id exists

def verify_params(params):
    if params is None:
        raise InputException("missing params")
    return {
        "account": verify_account(params)
    }

def fetch_eth_price():
    try:
        url = f"https://api.zapper.fi/v1/prices/0x0000000000000000000000000000000000000000?network=ethereum&timeFrame=hour&currency=USD&api_key=96e0cc51-a62e-42ca-acee-910ea7d2a241"
        response = requests.get(url, timeout=600)
        response.raise_for_status()
        res = response.json()
        # gives prices over the last hour, average
        prices = res["prices"]
        count = 0
        s = 0
        for price in prices:
            count += 1
            s += price[1]
        price = s / count
        if price <= 1000 or price >= 10000:
            throw("price out of range")
        return price
    except Exception as e:
        print(e)
        raise Exception("error fetching data")

def fetch_positions(params):
    try:
        api_key = "96e0cc51-a62e-42ca-acee-910ea7d2a241" # only key key, public
        url = f"https://api.zapper.fi/v1/balances?api_key={api_key}&addresses[]={params['account']}"
        response = requests.get(url, timeout=600)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(e)
        raise Exception("error fetching data")

def parse_positions(s):
    try:
        positions = []
        while True:
            index = s.find('{')
            index2 = s.find('}\n')
            if index == -1 or index2 == -1:
                break
            position = json.loads(s[index:index2+1])
            positions.append(position)
            s = s[index2+1:]
        # order by network, app
        positions = list(sorted(positions, key = lambda pos: f"{pos['network']} {pos['appId']}"))
        return positions
    except Exception as e:
        raise Exception("error parsing data")

def clean_positions(positions2, account):
    eth_price = fetch_eth_price()
    try:
        positions3 = []
        account = account.lower()
        for position in positions2:
            # filter out zero balance positions
            if len(position["balances"][account]["products"]) == 0:
                continue
            # filter out nfts and tokens
            if position["appId"] == "tokens" or position["appId"] == "nft":
                continue
            # flatten
            balanceUSD = 0
            for pos in position["balances"][account]["products"]:
                for asset in pos["assets"]:
                    balanceUSD += asset["balanceUSD"]
            position["balanceUSD"] = balanceUSD
            position["balanceETH"] = balanceUSD / eth_price
            position.pop("balances", None)
            positions3.append(position)
        return positions3
    except Exception as e:
        raise Exception("error parsing data")

def calculate_weights(positions):
    try:
        weighted_positions = []
        balance_sum = sum([position["balanceETH"] for position in positions])
        for position in positions:
            weighted_position = {"protocol": position["appId"], "weight": position["balanceETH"] / balance_sum}
            weighted_positions.append(weighted_position)
        return weighted_positions
    except Exception as e:
        raise Exception(f"error calculating weights. Error: {e}")

def get_scores(params):
    params2 = verify_params(params)
    positions = fetch_positions(params2)
    positions2 = parse_positions(positions)
    positions3 = clean_positions(positions2, params2["account"])
    positions4 = calculate_weights(positions3)
    # TODO: positions -> scores
    return json.dumps(positions4, indent=2)

def handler(event, context):
    try:
        response_body = get_scores(event["queryStringParameters"])
        return {
            "statusCode": 200,
            "body": response_body,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
