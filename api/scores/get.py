from api.utils import *
from datetime import datetime
import pandas as pd
import numpy as np
import json
import math

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
    # TODO: Lock in on field names for appId as 'address' isn't ideal atm
    if len(positions3) == 0:
        return {'address': params2["account"], 'protocols': positions3}
    for i in positions3:
        i['address'] = i['appId']
        i['symbol'] = i['network']
        del i['appId']
        del i['network']
    

    # local functions
    #
    def get_protocol(accountIn, portfolioInput, protocolMapInput, rateTableInput):
        # Left join protocols in account with known protocol tiers then remove nans
        scored_portfolio = pd.merge(portfolioInput,protocolMapInput, left_on='address', right_on='address',how='left')
        #scored_portfolio['tier'] = scored_portfolio['tier'].replace(np.nan, 'tier4')  # sets unknown protocol to highest risk tier 
        # log unknown protocols to S3
        #inds = pd.isnull(scored_portfolio['tier']).to_numpy().nonzero()
        indexInScoringDb = list(scored_portfolio.loc[pd.isna(scored_portfolio["tier"]), :].index)
        unknownProtocols = scored_portfolio.loc[indexInScoringDb, 'address']
        outputUnknownProtocols=[]
        if unknownProtocols.shape[0] > 0:
            outputUnknownProtocols = unknownProtocols.to_list()
            date_string = datetime.now(). strftime("%Y-%m-%d")
            s3_put("to-be-scored/"+date_string+"/"+accountIn+".json", json.dumps(outputUnknownProtocols))
        
        # uncomment for lambda
        #s3_put("to-be-scored/"+date_string+"/"+accountIn+".json", json.dumps(outputUnknownProtocols))
        scored_portfolio['tier'] = scored_portfolio['tier'].replace(np.nan, 'tier4')  # sets unknown protocol to highest risk tier 

        # aggregate portfolio positions by tier
        combinedTable = pd.merge(scored_portfolio,rateTableInput, left_on='tier', right_on='tier',how='left')
        rp_column = combinedTable['balanceUSD'] * combinedTable["rrol"]
        combinedTable['rp-usd'] = rp_column
        ra_column = combinedTable['rp-usd'] * combinedTable['riskLoad']
        combinedTable['risk-adj'] = ra_column
        return combinedTable
    #
    def calc_portfolio_score(correlMatInput, ra_column):
        for i in correlMatInput:
            if i.shape==(1,1):
                portfolioRateScore=ra_column
            else:
                correlMat=np.array([correlMatInput])
                #correlMat_values=correlMat_array[0,0:4,1:5]
                ra_line=np.array([ra_column])
                ra_column2=np.array([ra_column]).T
                #Calculate matmul in two steps for readabilityþ
                new_matrix=np.matmul(correlMat,ra_column2)
                portfolioRateScore=math.sqrt(np.matmul(ra_line,new_matrix))
            #print("Portfolio ROL in Base Currency: " + str(portfolioRPinBaseCurrency*portfolioRateScore))
        return portfolioRateScore
    #
    def create_category_table(rateTableInput):
        combinedTable4=rateTableInput.groupby(['category'])['risk-adj'].apply(lambda x: x.values.tolist()).tolist()# .tolist()
        return combinedTable4
    #
    def create_matrix(correlValue,countCategory,index):
        
        if countCategory!=0:                
            matrix=np.zeros(shape=(countCategory,countCategory))
            for j in range(countCategory):
                for k in range(countCategory):
                    if matrix[k][j]==matrix[j][k]:
                        matrix[k][j]=1
                    else:
                        matrix[k][j] = correlValue['correlation'][index]
                        matrix[j][k] = correlValue['correlation'][index]
            
            return matrix
    #
    def create_protocol_correlation(portfolioMap,correlValue):
        matrix_array=[]
        countCategory=portfolioMap['category'].value_counts()
        index=0
        for i in countCategory:
            matrixCat=create_matrix(correlValue,i,index)
            index+=1
            matrix_array.append(matrixCat)
        return matrix_array
    #
    def calc_rate_online(portfolioMap,protocolCorrelIn,ra_column,correlCatIn):
        N=len(protocolCorrelIn)
        categoryarray=[]
        #print(portfolioMap['category'].unique())
        #print('correlCatIn ',correlCatIn)
        for i in portfolioMap['category'].unique():
            if i in correlCatIn:
                categoryarray.append(correlCatIn[i]) 
        correlCatIn_values=np.array(categoryarray)
        #print('correlCatIn_values ',correlCatIn_values)
        ra_line=np.array([ra_column])
        ra_column2=np.array([ra_column]).T
        #print('this is ra_column2',ra_column2)
        #print('this is correlCatIn_values[0:N,0:N]',correlCatIn_values)
        new_matrix=np.matmul(correlCatIn_values[0:N,0:N],ra_column2)
        portfolioRateScore=math.sqrt(np.matmul(ra_line,new_matrix))       
        return portfolioRateScore

    def rate_engine(accountIn, positions):
        # Log the positions by account
        date_string = datetime.now(). strftime("%Y-%m-%d")
        s3_put("asked-for-quote/"+date_string+"/"+accountIn+".json", json.dumps(positions))
        
        # Get the published rate data and create dataframes
        correlCat_file = s3_get("current-rate-data/correlCat.json")
        correlCatJson_object = json.loads(correlCat_file)
        correlCat = pd.DataFrame(correlCatJson_object)

        protocolMap_file = s3_get("current-rate-data/protocolMap.json")
        protocolMap__object = json.loads(protocolMap_file)
        protocolMap = pd.DataFrame(protocolMap__object)

        # Get corr Value from S3
        corrValueFile = s3_get("current-rate-data/corrValue.json") # will be from S3 not local
        corrValueJson_object = json.loads(corrValueFile)
        correlValue=pd.DataFrame(corrValueJson_object)
        
        rateTableJson_file = s3_get("current-rate-data/rateTable.json")
        rateTableJson_object = json.loads(rateTableJson_file)
        rateTable = pd.DataFrame(rateTableJson_object)

        # Init a dataframe to store an account's positions
        
        portfolio = pd.DataFrame(positions)
        portfolio.columns =['balanceUSD', 'balance','address', 'network']

        #Portfolio of protocols
        balanceByTier = get_protocol(accountIn, portfolio, protocolMap, rateTable)
        balanceByTier['category'] = balanceByTier['category'].replace(np.nan, 'unrated')  

        #print(balanceByTier)

        # Aggregate risk loads based on category. Returns an array containing a risk load list for each category
        table=create_category_table(balanceByTier)
        #print(table)

        protocolCorrel=create_protocol_correlation(balanceByTier, correlValue)
        #print(protocolCorrelIn)

        risk_load_category=[]
        for i in range(0,len(protocolCorrel)):
            for j in range(0,len(protocolCorrel)):
                if len(protocolCorrel[i])==len(table[j]):
                    protocol_matrix=protocolCorrel[i]
                    risk_load_column=table[j]
                    risk_load_array=np.array(risk_load_column)
                    Score=calc_portfolio_score(protocol_matrix,risk_load_array)
                    if Score not in risk_load_category:
                        risk_load_category.append(Score)
        #print(risk_load_category)
        TotalScore=calc_rate_online(balanceByTier,protocolCorrel,risk_load_category, correlCat)
        #print(TotalScore)

        # Variables for the table:
        BalanceTotal=balanceByTier['balanceUSD'].sum()
        RpTotal=balanceByTier['rp-usd'].sum()
        TotalRate=RpTotal+TotalScore
        Rate_percentage=TotalRate/BalanceTotal

        # Table data 
        balanceByTier['json'] = balanceByTier.to_json(orient='records', lines=True).splitlines()       
        rateOut = {'address': accountIn,'addressRP':TotalRate,'currentRate':Rate_percentage,'protocols': list(map(json.loads, balanceByTier['json'].tolist()))}
        return rateOut

    
    rateCard = rate_engine(params["account"],positions3) 
    #print(rateCard)
    return json.dumps(rateCard, indent=2) 

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
