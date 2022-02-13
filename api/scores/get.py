from api.utils import *
from datetime import datetime
import pandas as pd
import numpy as np
import json
import math


def verify_positions(positions):
    # TODO: input sanitization
    positions_out = json.loads(positions)
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

def get_scores(account, positions):
    # check for empty porfolio
    if len(positions) == 0:
        return json.dumps({'address': account, 'protocols': []},indent=2)

    def get_protocol(portfolio_input, protocol_map_input, rate_table_input):
        # left join protocols in account with known protocol tiers then remove nans
        scored_portfolio = pd.merge(portfolio_input, protocol_map_input, left_on='appId', right_on='appId', how='left')
     
        # log unknown protocols to S3
        index_in_scoring_db = list(scored_portfolio.loc[pd.isna(scored_portfolio["tier"]), :].index)
        unknown_protocols = scored_portfolio.loc[index_in_scoring_db, 'appId']
        unknown_protocols = unknown_protocols.to_list()
        output_unknown_protocols = []
        for i in unknown_protocols:
            output_unknown_protocols.append(i)

        if len(output_unknown_protocols) > 0:
            date_string = get_date_string()
            s3_put(S3_TO_BE_SCORED_FOLDER + date_string + "/" + account + ".json", json.dumps({'unknown_protocols': output_unknown_protocols}))

        # sets unknown protocol to highest risk tier
        scored_portfolio['tier'] = scored_portfolio['tier'].replace(np.nan, 0)  

        # aggregate portfolio positions by tier
        combined_table = pd.merge(scored_portfolio, rate_table_input, left_on='tier', right_on='tier', how='left')
        rp_column = combined_table['balanceUSD'] * combined_table["rrol"]
        combined_table['rp-usd'] = rp_column
        ra_column = combined_table['rp-usd'] * combined_table['riskLoad']
        combined_table['risk-adj'] = ra_column
        return combined_table

    def calc_portfolio_score(correl_mat_input, ra_column):
        for i in correl_mat_input:
            if i.shape == (1,1):
                portfolio_rate_score = ra_column
            else:
                correl_mat = np.array(correl_mat_input)
                ra_line = np.array(ra_column)
                ra_column2 = np.array(ra_column).T

                # calculate matmul in two steps for readability
                new_matrix = np.matmul(correl_mat, ra_column2)
                portfolio_rate_score = math.sqrt(np.matmul(ra_line, new_matrix))
        return portfolio_rate_score

    def create_matrix(correl_value, count_category, index, key):
        if count_category != 0:
            matrix = np.zeros(shape=(count_category, count_category))
            for j in range(count_category):
                for k in range(count_category):
                    if matrix[k][j] == matrix[j][k]:
                        matrix[k][j] = 1
                    else:
                        matrix[k][j] = correl_value[key][index]
                        matrix[j][k] = correl_value[key][index]
            return matrix

    def risk_load_category(balance_by_tier, category):
        category_rates = balance_by_tier.groupby('category')['risk-adj'].apply(lambda x: x.values.tolist()).reset_index()
        risk_load_category = category_rates.loc[category_rates['category'] == category, 'risk-adj']
        return risk_load_category.tolist()

    def get_index(category, correl_value):
        result = np.where(correl_value == category)
        return result[0][0]

    def create_protocol_correlation(portfolio_map, correl_value):
        matrix_array = []
        risk_load_categories = []
        countCategory = portfolio_map['category'].value_counts()
        index = 0
        for k, v in countCategory.items():
            index = get_index(k, correl_value)
            matrix_cat = create_matrix(correl_value, v, index, 'correlation')
            matrix_array.append(matrix_cat)
            risk_load_array = risk_load_category(portfolio_map, k)
            risk_load_array2 = np.array(risk_load_array)
            score = calc_portfolio_score(matrix_cat, risk_load_array2)
            risk_load_categories.append(score)
        return  risk_load_categories

    def category_matrix(categories, correl_cat):
        indexes = []
        for i in categories:
            for j in categories:
                index2 = get_index(j, correl_cat) 
                value = correl_cat[i][index2]
                indexes.append(value)

        n = len(categories)
        indexes = np.array(indexes).reshape(n, n)
        return indexes

    def calc_rate_online(portfolio_map, ra_column, correl_cat):
        categories = portfolio_map['category'].unique()
        corr_cat = category_matrix(categories, correl_cat)

        ra_line = np.array(ra_column)
        ra_column2 = np.array(ra_column).T
        new_matrix = np.matmul(corr_cat,ra_column2)
        portfolio_rate_score = math.sqrt(np.matmul(ra_line, new_matrix))
        return portfolio_rate_score

    def rate_engine(account, positions):
        try:
            # log the positions by account
            date_string = get_date_string()
            s3_put(S3_ASKED_FOR_QUOTE_FOLDER + date_string + "/" + account + ".json", json.dumps(positions))

            # get the published rate data and create dataframes
            series_json_object = json.loads(s3_get(S3_SERIES_FILE, cache=True))
            rate_table = pd.DataFrame(series_json_object['data']['rateCard'])
            correl_cat = pd.DataFrame(series_json_object['data']['correlCat'])
            protocol_map = pd.DataFrame(series_json_object['data']['protocolMap'])
            correl_value = pd.DataFrame(series_json_object['data']['corrValue'])

            # init a dataframe to store an account's positions
            portfolio = pd.DataFrame(positions)
            portfolio.columns = ['appId', 'network','balanceUSD', 'balanceETH']

            # portfolio of protocols
            balance_by_tier = get_protocol(portfolio, protocol_map, rate_table)
            balance_by_tier['category'] = balance_by_tier['category'].replace(np.nan, 'unrated')
            
            risk_load_category = create_protocol_correlation(balance_by_tier, correl_value)
            total_score = calc_rate_online(balance_by_tier, risk_load_category, correl_cat)

            # Variables for the table:
            balance_total = balance_by_tier['balanceUSD'].sum()
            rp_total = balance_by_tier['rp-usd'].sum()
            total_rate = rp_total+total_score
            rate_percentage = total_rate/balance_total

            # TODO: remove when input format is locked. 
            # Clean up column name for return data DIRTFT FTW
            balance_by_tier.rename(columns={'protocol': 'appId'}, inplace=True)

            ############### Added for debugging ###############
            categories_in_portfolio2 = balance_by_tier['category'].unique()
            categories_in_portfolio3 = balance_by_tier.groupby('category')['risk-adj'].sum()
            df4 = pd.DataFrame(categories_in_portfolio3)
            df4['TotalScore'] = total_score

            for _ in categories_in_portfolio2:
                staked_cover = rp_total + sum(categories_in_portfolio3)

            stacked_cover_rate = staked_cover / balance_total
            discount = (rate_percentage / stacked_cover_rate) - 1

            # table data
            data2 = {'Type': ['Address Cover', 'Stacked Cover', 'Discount'], 'RP':[total_rate, staked_cover, discount], 'ROL':[rate_percentage, stacked_cover_rate,'']}  
            df3 = pd.DataFrame(data2) 
            df3.head()
            
            # table data
            balance_by_tier['json'] = balance_by_tier.to_json(orient='records', lines=True).splitlines()
            rate_out = { 
                'address': account, 
                'address_rp': total_rate,
                'current_rate': rate_percentage,
                'timestamp': get_timestamp(),
                'protocols': list(map(json.loads, balance_by_tier['json'].tolist())),
                'metadata': series_json_object['metadata']
            }
            return rate_out
        except Exception as e:
            print(e)
            return None

    rate_card = rate_engine(account, positions)
    if rate_card is None:
        print(f"Unexpected error occurred while calculating rate for {account}. Please refer logs to investigate")
        return None
    return json.dumps(rate_card, indent=2)

def handler(event, context):
    try:
        account, positions = verify_positions(event["body"])
        response_body = get_scores(account, positions)

        if response_body is None:
            return {
                "statusCode": 400,
                "body": {"message": "Error"},
                "headers": headers
            }
            
        return {
            "statusCode": 200,
            "body": response_body,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)
