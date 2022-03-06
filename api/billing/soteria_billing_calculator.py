import asyncio
from api.utils import *
import json
import pandas as pd
import numpy as np
from datetime import datetime


# util to convert nested json to flat dataframe
def flatten_nested_json_df(df):
    df = df.reset_index()

    # search for columns to explode/flatten
    s = (df.applymap(type) == list).all()
    list_columns = s[s].index.tolist()

    s = (df.applymap(type) == dict).all()
    dict_columns = s[s].index.tolist()

    while len(list_columns) > 0 or len(dict_columns) > 0:
        new_columns = []

        for col in dict_columns:
            #print(f"flattening: {col}")
            # explode dictionaries horizontally, adding new columns
            horiz_exploded = pd.json_normalize(df[col]).add_prefix(f'{col}.')
            horiz_exploded.index = df.index
            df = pd.concat([df, horiz_exploded], axis=1).drop(columns=[col])
            new_columns.extend(horiz_exploded.columns) # inplace

        for col in list_columns:
            #print(f"exploding: {col}")
            # explode lists vertically, adding new columns
            df = df.drop(columns=[col]).join(df[col].explode().to_frame())
            new_columns.append(col)

        # check if there are still dict o list fields to flatten
        s = (df[new_columns].applymap(type) == list).all()
        list_columns = s[s].index.tolist()

        s = (df[new_columns].applymap(type) == dict).all()
        dict_columns = s[s].index.tolist()
    return df


async def calculate_bill(score_file: str, policyholder: str):
    try:
        print(f"Calculating premium for policyholder: {policyholder}. Score file: {score_file}")
        scores = json.loads(s3_get(score_file))

        df = pd.DataFrame.from_dict(scores)
        flat_df1 = flatten_nested_json_df(df)
        flat_df1['timeStamp'] = pd.to_datetime(flat_df1['scores.timestamp'])

        g1 = pd.DataFrame({'count': flat_df1.groupby(['timeStamp', 'scores.score.protocols.balanceUSD', 'scores.coverlimit', 'scores.score.current_rate']).size()}).reset_index()
        sub1 = pd.DataFrame(g1.groupby('timeStamp')[['scores.score.protocols.balanceUSD']].sum())
        sub2 = pd.DataFrame(g1.groupby('timeStamp')[['scores.coverlimit','scores.score.current_rate']].max())
        sub2['portfolioBalanceUSD'] = sub1

        # Make sure the timestamp is sorted old to new
        sub2.sort_values(by='timeStamp', ascending=True, kind='quicksort', inplace=True)
        # Which amount to bill? Coverlimit or Portfolio Balance? Always whats best for policy holder
        sub2['amountCovered'] = np.where(sub2['scores.coverlimit'] <= sub2['portfolioBalanceUSD'], sub2['scores.coverlimit'], sub2['portfolioBalanceUSD'])

        # Calculate the amount of exposure time
        sub2 = sub2.reset_index()
        sub2['timeExposed'] = sub2['timeStamp'].diff()
        sub2['secondsExposed'] = sub2['timeExposed'].dt.total_seconds().shift(-1)
        sub2['timeExposed'] = sub2['timeExposed'].shift(-1)
        sub2['yearsExposed']= sub2['secondsExposed'] / 3.154e+7  #seconds in a year

        # Calculate the premium utilized during the exposure period
        sub2['trueUpPremium'] = sub2['yearsExposed'] * sub2['scores.score.current_rate'] * sub2['amountCovered']
        sub2.rename(columns={'scores.coverlimit': 'coverLimit', 'scores.score.current_rate': 'currentRate'}, inplace=True)
        sub2 = sub2[['timeStamp', 'coverLimit', 'portfolioBalanceUSD', 'amountCovered', 'currentRate', 'timeExposed', 'secondsExposed', 'yearsExposed','trueUpPremium']]

        # Calculate the grand total trueUpPremium to be billed oncahin
        total_due = sub2['trueUpPremium'].sum()
        timestamp = sub2['timeStamp'].iloc[-1]
        return {"timestamp": str(timestamp), "premium": total_due, "created_time": get_timestamp(), "charged": False, "charged_time": ""}, policyholder, score_file
    except Exception as e:
        return None, policyholder, score_file


async def archive_score_file(score_file: str, chain_id: str):
    date_folder = get_date_string()
    filename = get_file_name(score_file)
    new_key = S3_SOTERIA_PROCESSED_SCORES_FOLDER + chain_id + "/" + date_folder + "/" + filename + ".json"
    s3_move(score_file, new_key)


async def calculate_bills():
    for chain_id in get_supported_chains():
        print(f"Calculating soteria billings for chain {chain_id} has been started....")
        try:
            billings = get_soteria_billings(chain_id=chain_id)
            billing_errors = get_billing_errors(chain_id=chain_id)
            score_files = get_soteria_score_files(chain_id=chain_id)
          
            if len(score_files) == 0:
                print(f"No score file is found for chain {chain_id}")
                continue

            tasks = []
            for score_file in score_files:
                policyholder = get_file_name(score_file)
                tasks.append(asyncio.create_task(calculate_bill(score_file, policyholder)))

            completed_tasks, _ = await asyncio.wait(tasks)
            for completed_task in completed_tasks:
                result = completed_task.result()
                premium = result[0]
                policyholder = result[1]
                score_file = result[2]

                if premium is None:
                    print(f"Error occurred while calculating the premium for policyholder: {policyholder}")
                    if policyholder not in billing_errors:
                        billing_errors[policyholder] = []
                    billing_errors[policyholder].append({'score_file': score_file, 'timestamp': get_timestamp()})
                    continue

                if policyholder not in billings:
                    billings[policyholder] = []
            
                already_calculated = list(filter(lambda p: p['timestamp'] == premium['timestamp'], billings[policyholder]))
                if len(already_calculated) > 0:
                    print(f"Premium has been already calculated for policyholder {policyholder}. Premium info: {premium}")
                    continue

                billings[policyholder].append(premium)
                print(f"Premium has been calculated for policyholder: {policyholder}. Premium info: {premium}")

                # archive score file
                await archive_score_file(score_file, chain_id)
            
            # save results
            save_billings(chainId=chain_id, billings=billings)
            save_billing_errors(chainId=chain_id, billing_errors=billing_errors)
            print(f"Calculating soteria billings for chain {chain_id} has been finished.")
        except Exception as e:
            print(f"Error occurred while calculating bills: Error: {e}")

def main(event, context):
    asyncio.run(calculate_bills())

if __name__ == '__main__':
    main(None, None)