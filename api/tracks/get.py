from api.utils import *

def get_scores_by_account(chain_id: str, account: str):
    try:
        score_file = get_soteria_score_file(chain_id, account)
        if score_file:
            scores = json.loads(score_file)
            return scores
        return []
    except Exception as e:
        handle_error({"resource": "tracks.get_scores_by_account()"}, e, 500)
        return None

def handler(event, context):
    try:
        params = event["queryStringParamaters"]
        __verify_chain_id(params=params)
        __verify_account(params=params)

        chain_id = params["chain_id"]
        account = params["account"]
        scores = get_scores_by_account(chain_id=chain_id, account=account)
        if scores:
            return __response({'chain_id': chain_id, 'account': account, 'scores': scores["scores"]})
        else:
            return __error_response()
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)

def __error_response():
    return json.dumps({
        "status_code": 500,
        "result": {"message": "Something went wrong"}
    })

def __response(result):
    return json.dumps({
        "status_code": 200,
        "result": result
    })

def __verify_chain_id(params):
    if "chain_id" not in params:
        raise InputException("Chain id must be provided")

    chain_id = params["chain_id"]
    if chain_id not in get_supported_chains():
        raise InputException(f"Chain Id: {chain_id} is not supported yet")

def __verify_account(params):
    if "account" not in params:
        raise InputException("Account address must be provided")
