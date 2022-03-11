from api.utils import *

def get_scores_by_account(chain_id: str, account: str):
    try:
        score_file = get_soteria_score_file(chain_id, account)
        if score_file:
            scores = json.loads(score_file)
            return scores
        return {"scores": []}
    except Exception as e:
        handle_error({"resource": "tracks.get_scores_by_account()"}, e, 500)
        return None

def handler(event, context):
    try:
        print(type(event))
        params = event["queryStringParameters"]
        __verify_chain_id(params=params)
        __verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        scores = get_scores_by_account(chain_id=chain_id, account=account)
        if scores is not None:
            return __response({'chain_id': chain_id, 'account': account, 'scores': scores["scores"]})
        else:
            return __error_response()
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def __error_response():
    return {
        "statusCode": 500,
        "body": {"message": "Something went wrong"},
        "headers": headers
    }

def __response(result):
    return {
        "statusCode": 200,
        "body": json.dumps(result),
        "headers": headers
    }

def __verify_chain_id(params):
    if "chain_id" not in params:
        raise InputException("Chain id must be provided")

    chain_id = params["chain_id"]
    if chain_id not in get_supported_chains():
        raise InputException(f"Chain Id: {chain_id} is not supported yet")

def __verify_account(params):
    if "account" not in params:
        raise InputException("Account address must be provided")
