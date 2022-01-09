from api.utils import *
from datetime import datetime
import pandas as pd
import numpy as np
import json
import math


def verify_positions(positions_in):
    # TODO: input sanitization
    positions_out = json.loads(positions_in)
    account = positions_out['account']
    positions_out = positions_out['positions']
    return account, positions_out

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

def get_scores(event):
    account, positions = verify_positions(event["body"])
    #Check for empty porfolio
    if len(positions) == 0:
        return json.dumps({'address': account, 'protocols': []},indent=2)

    # local functions
    #
    def get_protocol(portfolioInput, protocolMapInput, rateTableInput):
        # Left join protocols in account with known protocol tiers then remove nans
        scored_portfolio = pd.merge(portfolioInput,protocolMapInput, left_on='appId', right_on='appId',how='left')
        # log unknown protocols to S3
        #inds = pd.isnull(scored_portfolio['tier']).to_numpy().nonzero()
        indexInScoringDb = list(scored_portfolio.loc[pd.isna(scored_portfolio["tier"]), :].index)
        unknownProtocols = scored_portfolio.loc[indexInScoringDb, 'appId']
        outputUnknownProtocols=[]
        for i in unknownProtocols:
            outputUnknownProtocols = unknownProtocols.to_list()
            outputUnknownProtocols.append(i)
            date_string = datetime.now(). strftime("%Y-%m-%d")
            #s3_put("to-be-scored/"+date_string+"/"+accountIn+".json", json.dumps(outputUnknownProtocols))

        # uncomment for lambda
        #s3_put("to-be-scored/"+date_string+"/"+accountIn+".json", json.dumps(outputUnknownProtocols))
        scored_portfolio['tier'] = scored_portfolio['tier'].replace(np.nan, 0)  # sets unknown protocol to highest risk tier

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
                correlMat=np.array(correlMatInput)
                ra_line=np.array(ra_column)
                ra_column2=np.array(ra_column).T
                #Calculate matmul in two steps for readability
                new_matrix=np.matmul(correlMat,ra_column2)
                portfolioRateScore=math.sqrt(np.matmul(ra_line,new_matrix))
        return portfolioRateScore

    #
    def create_matrix(correlValue,countCategory,index,key):

        if countCategory!=0:
            matrix=np.zeros(shape=(countCategory,countCategory))
            for j in range(countCategory):
                for k in range(countCategory):
                    if matrix[k][j]==matrix[j][k]:
                        matrix[k][j]=1
                    else:
                        matrix[k][j] = correlValue[key][index]
                        matrix[j][k] = correlValue[key][index]

            return matrix
    def riskLoadCategory(balancebyTier,category):
    
        categoryRates=balancebyTier.groupby('category')['risk-adj'].apply(lambda x: x.values.tolist()).reset_index()

        risk_load_category=categoryRates.loc[categoryRates['category']==category,'risk-adj']
        
        return risk_load_category.tolist()

    def get_index(category,correlValue):
        result=np.where(correlValue==category)
        return result[0][0]

    #
    def create_protocol_correlation(portfolioMap,correlValue):
        matrix_array=[]
        risk_load_category=[]
        countCategory=portfolioMap['category'].value_counts()
        index=0
        for k,v in countCategory.items():
            index=get_index(k,correlValue)
            matrixCat=create_matrix(correlValue,v,index,'correlation')
            matrix_array.append(matrixCat)
            risk_load_array=riskLoadCategory(portfolioMap,k)
            risk_load_array2=np.array(risk_load_array)
            Score=calc_portfolio_score(matrixCat,risk_load_array2)
            risk_load_category.append(Score)
            
        return  risk_load_category

        ##f
    def category_matrix(categories,correlCat):
        indexes=[]
        for i in categories:
            for j in categories:
                index2=get_index(j,correlCat) 
                value=correlCat[i][index2]
                indexes.append(value)

        N=len(categories)
        indexs=np.array(indexes).reshape(N,N)
        return indexs
    #
    def calc_rate_online(portfolioMap,ra_column,correlCat):
        N=len(ra_column)
        categories=portfolioMap['category'].unique()
        corrCat=category_matrix(categories,correlCat)

        ra_line=np.array(ra_column)
        ra_column2=np.array(ra_column).T
        new_matrix=np.matmul(corrCat,ra_column2)
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
        portfolio.columns =['network', 'appId','balanceUSD', 'balanceETH']
        #Portfolio of protocols
        balanceByTier = get_protocol(portfolio, protocolMap, rateTable)
        balanceByTier['category'] = balanceByTier['category'].replace(np.nan, 'unrated')
        
        risk_load_category=create_protocol_correlation(balanceByTier, correlValue)
        TotalScore=calc_rate_online(balanceByTier,risk_load_category, correlCat)
        
        #print(TotalScore)

        # Variables for the table:
        BalanceTotal=balanceByTier['balanceUSD'].sum()
        RpTotal=balanceByTier['rp-usd'].sum()
        TotalRate=RpTotal+TotalScore
        Rate_percentage=TotalRate/BalanceTotal

        # TODO: remove when input format is locked. 
        # Clean up column name for return data DIRTFT FTW
        balanceByTier.rename(columns={'protocol': 'appId'}, inplace=True)

        ############### Added for debugging ###############
        categories_in_portfolio2=balanceByTier['category'].unique()
        categories_in_portfolio3=balanceByTier.groupby('category')['risk-adj'].sum()
        df4=pd.DataFrame(categories_in_portfolio3)
        df4['TotalScore']=TotalScore
        #print(df4)
        for i in categories_in_portfolio2:
            StackedCover=RpTotal+sum(categories_in_portfolio3)
        StackedCoverRate=StackedCover/BalanceTotal
        discount=(Rate_percentage/StackedCoverRate)-1
        # Table data
        data2 = {'Type':['Address Cover', 'Stacked Cover', 'Discount'], 'RP':[TotalRate, StackedCover, discount],'ROL':[Rate_percentage,StackedCoverRate,'']}  
        df3 = pd.DataFrame(data2) 
        df3.head()
        #print(df3)
        # Table data
        balanceByTier['json'] = balanceByTier.to_json(orient='records', lines=True).splitlines()
        rateOut = {'address': accountIn,'addressRP':TotalRate,'currentRate':Rate_percentage,'protocols': list(map(json.loads, balanceByTier['json'].tolist()))}
        return rateOut


    rateCard = rate_engine(account, positions)
    return json.dumps(rateCard, indent=2)

#comment
def handler(event, context):
    try:
        response_body = get_scores(event)
        return {
            "statusCode": 200,
            "body": response_body,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)