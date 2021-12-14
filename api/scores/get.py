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

def fetch_positions(params):
    try:
        api_key = "96e0cc51-a62e-42ca-acee-910ea7d2a241" # only key key, public
        url = f"https://api.zapper.fi/v1/balances?api_key={api_key}&addresses[]={params['account']}"
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(e)
        raise Exception("error fetching data")

def parse_positions(s, account):
    try:
        positions = []
        account = account.lower()
        while True:
            index = s.find('{')
            index2 = s.find('}\n')
            if index == -1 or index2 == -1:
                break
            position = json.loads(s[index:index2+1])
            # filter out zero balance positions
            if len(position["balances"][account]["products"]) > 0:
                positions.append(position)
            s = s[index2+1:]
        return positions
    except Exception as e:
        raise Exception("error parsing data")

def get_scores(params):
    params2 = verify_params(params)
    positions = fetch_positions(params2)
    positions = parse_positions(positions, params2["account"])
    # TODO: positions -> scores
    return json.dumps(positions, indent=2)

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
