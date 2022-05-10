from api.utils import *
from datetime import datetime, timedelta


def __get_thickers(params):
    tickers = []
    if "tickers" not in params:
        return tickers
        
    for ticker in params["tickers"].split(","):
        if len(ticker) > 0:
            tickers.append(ticker.strip().upper())
    return tickers

def __calculate_price_change(prev_price_data: dict, curr_price_data: dict):
    prev_price = prev_price_data["price"]
    curr_price = curr_price_data["price"]
    #diff = abs(curr_price - prev_price)
    change = float(curr_price / prev_price)
    return {"date": curr_price_data["date"], "price": curr_price,  "change": change}

def get_price_history(params):
    try:
        tickers = __get_thickers(params)
        start_date = get_date_string()
        end_date = get_date_string()

        window = 7
        if "window" in params:
            try:
                window = int(params["window"])
            except:
                print(f"window param { params['window'] } is not valid")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=window)
        start_date = start_date.strftime("%Y-%m-%d")
        end_date = end_date.strftime("%Y-%m-%d")

        result = {}
        for ticker in tickers:
           print(f"Getting price info for ticker: {ticker}")
           url = f"https://api.covalenthq.com/v1/pricing/historical/USD/{ticker}/?quote-currency=USD&format=JSON&from={start_date}&to={end_date}&key={COVALENT_API_KEY}"

           response = requests.get(url, timeout=600)
           response.raise_for_status()
           response = response.json()
           response = response["data"]
           
           # get price history
           result[ticker] = list(map(lambda price: {"date": price["date"], "price": price["price"]}, response["prices"]))
           
           # calculate price change
           result[ticker] = [__calculate_price_change(result[ticker][i-1], result[ticker][i]) for i in range(1, len(result[ticker])-1)]

        return result
    except Exception as e:
            msg = f"In Solace Risk API get price history. Error fetching price history for {ticker}\nURL   : {url}\nIP    : {get_IP_address()}\nError : {e}"
            print(msg)
            sns_publish(msg)
    return {}

def handler(event, context):
    try:
        params = event["queryStringParameters"]
        if params is None:
            result = {}
        else:
            result = get_price_history(params)

        return {
            "statusCode": 200,
            "body": json.dumps(result),
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
