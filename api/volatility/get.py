from api.utils import *
from api.pricehistory.get import get_price_history
from datetime import  date
import scipy
import pandas as pd
import numpy as np
from metalog import metalog
import json
import sys


"""
    Code borrowed from https://github.com/probability-management/PySIPmath/blob/main/PySIP/PySIP3library.py    
"""
def portfolio_shaper(SIPdata, SIPmetadata = [], dependence = 'independent', boundedness = 'u', bounds = [0, 1], term_saved = 5, seeds = [], setupInputs = []):
    if (seeds != [] and len(seeds) < len(SIPdata.columns)):
        print("RNG list length must be equal to or greater than the number of SIPs.")
    elif (setupInputs != [] and len(setupInputs["bounds"]) != len(SIPdata.columns)):
        print("List length of the input file must be equal to the number of SIPs.")
    else:
        slurp = SIPdata #Assigning some useful variables
        sip_count = len(slurp.columns)
        
        if seeds == []: #This section will create a random seed value for each SIP, or use an input 'rng' list
            rand = np.random.randint(1,10000001)
            Seeds = [1, rand, 0, 0]    
            rngs=list()
            for i in range(sip_count):
                rngs.append({'name':'hdr'+str(i+1),
                           'function':'HDR_2_0',
                           'arguments':{'counter':'PM_Index',
                               'entity': Seeds[0],
                               'varId': Seeds[1]+i,
                               'seed3': Seeds[2],
                               'seed4': Seeds[3]}
                           })
        else:
            rngs=seeds
        
         #More set up to hold the copula information
        rng = list()
        for i in range(sip_count):
            rng.append('hdr'+str(i+1))
        copulaLayer = list()
        for i in range(sip_count):
            copulaLayer.append('c'+str(i+1))
        
        arguments={'correlationMatrix':{'type':'globalVariables',
                        'value':'correlationMatrix'},
                   'rng' : rng}
        
        copdict = {'arguments':arguments,
                   'function':'GaussianCopula',
                   'name':'Gaussian',
                   'copulaLayer' : copulaLayer}
        
        copula=list()
        copula.append(copdict)
        rng=rngs
        
        if dependence == 'dependent': #Holds the RNG and copula data if applicable
            oui ={'rng':rng,
                  'copula':copula}
        else:
            oui ={'rng':rng}
        
        if SIPmetadata == []: #If the describe function is being used for default metadata, then the names are being changed for the visual layer
            slurp_meta = pd.DataFrame(slurp.describe())
            renames = slurp_meta.index.values
            renames[4] = 'P25'
            renames[5] = 'P50'
            renames[6] = 'P75'
        else:
            slurp_meta = SIPmetadata
            
        if setupInputs == []:
            boundednessin = [boundedness] * sip_count
            if boundedness == 'u':
                boundsin = [[0,1]] * sip_count
            else:
                boundsin = [bounds] * sip_count
            termsin = [term_saved] * sip_count
        else:
            boundednessin = setupInputs['boundedness']
            boundsin = setupInputs['bounds']
            for i in range(sip_count):
                if boundednessin[i] == 'u':
                    boundsin[i] = [0,1]
            termsin = setupInputs['term_saved']
        metadata = slurp_meta.to_dict()
        sips=list()#Set up for the SIPs
        
        if dependence == 'dependent':#This section creates the metalogs for each SIP, and has a different version for the indepedent vs dependent case
            for i in range(sip_count):
                mfitted = metalog.fit(np.array(slurp.iloc[:,i]).astype(float), bounds = boundsin[i], boundedness = boundednessin[i], term_limit = termsin[i], term_lower_bound = termsin[i])
                interp = scipy.interpolate.interp1d(mfitted['M'].iloc[:,1],mfitted['M'].iloc[:,0])
                interped = interp(np.linspace(min(mfitted['M'].iloc[:,1]),max(mfitted['M'].iloc[:,1]),25)).tolist()
                a_coef = mfitted['A'].iloc[:,1].to_list()
                metadata[slurp.columns[i]].update({'density':interped})
                if boundednessin[i] == 'u':
                    sipdict = {'name':slurp.columns[i],
                        'ref':{'source':'copula',
                               'name':'Gaussian',
                               'copulaLayer':'c'+str(i+1)},
        	     	    'function':'Metalog_1_0',
                        'arguments':{'aCoefficients':a_coef},
                        'metadata':metadata[slurp.columns[i]]}
                if boundednessin[i] == 'sl':
                    sipdict = {'name':slurp.columns[i],
                        'ref':{'source':'copula',
                               'name':'Gaussian',
                               'copulaLayer':'c'+str(i+1)},
        	     	    'function':'Metalog_1_0',
                        'arguments':{'lowerBound':boundsin[i][0],
                                     'aCoefficients':a_coef},
                        'metadata':metadata[slurp.columns[i]]}
                if boundednessin[i] == 'su':
                    sipdict = {'name':slurp.columns[i],
                        'ref':{'source':'copula',
                               'name':'Gaussian',
                               'copulaLayer':'c'+str(i+1)},
        	     	    'function':'Metalog_1_0',
                        'arguments':{'upperBound':boundsin[i][0],
                                     'aCoefficients':a_coef},
                        'metadata':metadata[slurp.columns[i]]}
                if boundednessin[i] == 'b':
                    sipdict = {'name':slurp.columns[i],
                        'ref':{'source':'copula',
                               'name':'Gaussian',
                               'copulaLayer':'c'+str(i+1)},
        	     	    'function':'Metalog_1_0',
                        'arguments':{'lowerBound':boundsin[i][0],
                                     'upperBound':boundsin[i][1],
                                     'aCoefficients':a_coef},
                        'metadata':metadata[slurp.columns[i]]}
                sips.append(sipdict)
        else:
            for i in range(sip_count):
                mfitted = metalog.fit(np.array(slurp.iloc[:,i]).astype(float), bounds = boundsin[i], boundedness = boundednessin[i], term_limit = termsin[i], term_lower_bound = termsin[i])
                interp = scipy.interpolate.interp1d(mfitted['M'].iloc[:,1],mfitted['M'].iloc[:,0])
                interped = interp(np.linspace(min(mfitted['M'].iloc[:,1]),max(mfitted['M'].iloc[:,1]),25)).tolist()
                a_coef = mfitted['A'].iloc[:,1].to_list()
                metadata[slurp.columns[i]].update({'density':interped})
                if boundednessin[i] == 'u':
                    sipdict = {'name':slurp.columns[i],
                        'ref':{'source':'rng',
                               'name':'hdr'+str(i+1)},
        	     	    'function':'Metalog_1_0',
                        'arguments':{'aCoefficients':a_coef},
                        'metadata':metadata[slurp.columns[i]]}
                if boundednessin[i] == 'sl':
                    sipdict = {'name':slurp.columns[i],
                        'ref':{'source':'rng',
                               'name':'hdr'+str(i+1)},
        	     	    'function':'Metalog_1_0',
                        'arguments':{'lowerBound':boundsin[i][0],
                                     'aCoefficients':a_coef},
                        'metadata':metadata[slurp.columns[i]]}
                if boundednessin[i] == 'su':
                    sipdict = {'name':slurp.columns[i],
                        'ref':{'source':'rng',
                               'name':'hdr'+str(i+1)},
        	     	    'function':'Metalog_1_0',
                        'arguments':{'upperBound':boundsin[i][0],
                                     'aCoefficients':a_coef},
                        'metadata':metadata[slurp.columns[i]]}
                if boundednessin[i] == 'b':
                    sipdict = {'name':slurp.columns[i],
                        'ref':{'source':'rng',
                               'name':'hdr'+str(i+1)},
        	     	    'function':'Metalog_1_0',
                        'arguments':{'lowerBound':boundsin[i][0],
                                     'upperBound':boundsin[i][1],
                                     'aCoefficients':a_coef},
                        'metadata':metadata[slurp.columns[i]]}
                sips.append(sipdict)          
        
        corrdata = pd.DataFrame(np.tril(slurp.corr()))#Creating the lower half of a correlation matrix for the copula section if applicable
        corrdata.columns = slurp.columns
        corrdata.index = slurp.columns
        stackdf = corrdata.stack()
        truncstackdf = stackdf[stackdf.iloc[:] != 0]
        counter = truncstackdf.count()
    
        matrix = list()    
        for i in range(counter): #Gets our correlations in the correct format
            matrix.append({'row':truncstackdf.index.get_level_values(0)[i],
                  'col':truncstackdf.index.get_level_values(1)[i],
                  'value':truncstackdf[i]})
            
        
        value = {'columns' : slurp.columns.to_list(),
                 'rows' : slurp.columns.to_list(),
                 'matrix' : matrix}
        
        if dependence == 'dependent':#No global variables are added to the independent case
            globalVariables = list()
            globalVariables.append({'name':'correlationMatrix',
                                    'value':value})   
            
            finaldict = {
                         'objectType': 'sipModel',
                         'libraryType': 'SIPmath_3_0',
                         'dateCreated' : date.today().strftime("%m-%d-%Y"),
                         'globalVariables':globalVariables,
                         'U01' : oui,
                         'sips':sips,
                         'version':'1'}
        else:
            finaldict = {
                         'objectType': 'sipModel',
                         'libraryType': 'SIPmath_3_0',
                         'dateCreated' : date.today().strftime("%m-%d-%Y"),
                         'U01' : oui,
                         'sips':sips,
                         'version':'1'}
        return finaldict

def __get_terms(params):
    if "terms" not in params:
        return 3        
    
    if int(params['terms']) < 3 or int(params['terms']) > 30:
        return 3

    try:
        return int(params['terms'])
    except:
        return 3

def __create_cache_filename(params):
    cache_file = ''
    if "tickers" not in params:
        return None
        
    for ticker in params["tickers"].split(","):
        if len(ticker) > 0:
            cache_file = cache_file + ticker.strip().upper() + "_"

    cache_file += str(__get_terms(params)) + "_"

    window = 7
    if "window" in params:
            try:
                window = int(params["window"])
            except:
                pass
    cache_file += str(window) + '.json'
    return cache_file


def read_from_cache(filename):
    try:
        if filename is None:
            return None

        print('Cache file: ', S3_VOLATILITY_CACHE_FOLDER + filename)
        result = json.loads(s3_get(S3_VOLATILITY_CACHE_FOLDER + filename))

        if 'latest_access' not in result:
            return None
        
        if 'data' not in result:
            return None

        latest_access = datetime.strptime(result['latest_access'], "%Y-%m-%d, %H:%M:%S")
        current_time = datetime.now()
        diff = current_time - latest_access
        if (diff.seconds / 3600) > 1:
            return None
        return result['data']

    except Exception as e:
        print(f"Error occurred while getting cache file {filename}")
        return None

def get_volatility(params):
    try:
        # check cache
        cache_file = __create_cache_filename(params)
        cache_result = read_from_cache(cache_file)
        if cache_result is not None:
            return cache_result
         
        result = {}
        # get price history
        price_history = get_price_history(params)

        # normalize price history
        min_length = sys.maxsize        
        for value in price_history.values():
            if len(value) < min_length:
                min_length = len(value)

        
        for k in price_history.keys():
            price_history[k] = price_history[k][0:min_length]

        # get price change
        price_change = {}
        for k, v in price_history.items():
            price_change[k] = [value['change'] for value in v]

        # convert to df
        price_change = pd.DataFrame(price_change)

        # get terms input parameter
        terms = __get_terms(params)

        # call portfolio shaper
        result = portfolio_shaper(SIPdata=price_change, SIPmetadata=[], dependence='dependent', boundedness='u', bounds=[], term_saved=terms, seeds=[], setupInputs=[])

        # cache results
        cache = {'latest_access': datetime.now().strftime("%Y-%m-%d, %H:%M:%S"), 'data': result}
        s3_put(S3_VOLATILITY_CACHE_FOLDER + cache_file, json.dumps(cache))

        # return results
        return result
    except Exception as e:
            print(e)
            msg = f"In Solace Risk API get volatility. Error getting volatility. IP    : {get_IP_address()}\nError : {e}"
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
