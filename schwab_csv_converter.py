import datetime
import collections
import functools

input_filename = 'schwab_original.csv'
output_filename = 'filtered_schwab.csv'


def convertSchwabActionToSupportedAction(action):
    if (action == 'Stock Split'):
        return 'SPLIT'
    return action.upper()


def defineManualStockSplit(chunks):
    mm_dd_yyyy_date = chunks[0][0:10] # taking first 10 chars (mm/dd/yyyy) as some activities have
    #  weird date formatting
    dd_mm_yyyy_date = datetime.datetime.strptime(mm_dd_yyyy_date, "%m/%d/%Y").strftime("%d/%m/%Y")
    company_name = chunks[2]

    output_line = dd_mm_yyyy_date + " " + company_name + " "
    if (dd_mm_yyyy_date == "20/07/2021" and company_name == "NVDA"):
        multiplier = "4"

    if (dd_mm_yyyy_date == "31/08/2020" and company_name == "TSLA"):
        multiplier = "5"

    if (dd_mm_yyyy_date == "31/08/2020" and company_name == "AAPL"):
        multiplier = "4"

    print("handling split for ", chunks)
    return "SPLIT " + output_line + multiplier


# Output is a 2D dict of year -> month -> gbp to usd rate
# @functools.lru_cache(maxsize=None) # this does memoization
def getGbpUsdConversionMap():
    gbp_usd_file = "gbp_usd.csv"
    year_month_rate_dict = collections.defaultdict(dict)
    with open(gbp_usd_file) as file:
        lines = file.readlines()
        lines = [line.rstrip().lstrip() for line in lines]

    for line in lines:
        chunks = [word.replace("\"", "") for word in line.split(',')]
        date_chunks = [x for x in chunks[0].split('/')]
        month = date_chunks[0]
        year = date_chunks[1]
        gbp_usd_rate = chunks[1]
        if year in year_month_rate_dict:
            year_month_rate_dict[year][month] = gbp_usd_rate
        else:
            year_month_rate_dict[year] = {month: gbp_usd_rate}

    return year_month_rate_dict

# get rate from dd/mm/yyyy date
def getGbpUsdRateFromDate(dd_mm_yyyy_date):
    gbp_usd_map = getGbpUsdConversionMap()
    chunks = dd_mm_yyyy_date.split('/')
    month = chunks[1]
    year = chunks[2]
    # print('month is ', month, ' and year is ', year)
    # print('map is ', gbp_usd_map)
    # print('date is ', dd_mm_yyyy_date)
    return float(gbp_usd_map[year][month])


def handleBuySellLine(chunks):
    mm_dd_yyyy_date = chunks[0][0:10] # taking first 10 chars (mm/dd/yyyy) as some activities have
    #  weird date formatting
    dd_mm_yyyy_date = datetime.datetime.strptime(mm_dd_yyyy_date, "%m/%d/%Y").strftime("%d/%m/%Y")
    action = convertSchwabActionToSupportedAction(chunks[1])
    company_name = chunks[2]
    num_shares = chunks[4]
    dollar_value = chunks[5].replace("$", "")
    gbp_usd_rate = getGbpUsdRateFromDate(dd_mm_yyyy_date)
    # "{:.2f}".format ensures that only 2 decimal points are printed
    value = "{:.2f}".format(float(chunks[5].replace("$", "")) * 1.0/getGbpUsdRateFromDate(dd_mm_yyyy_date))
    fee = '0'
    tax = '0'
    words = [action, dd_mm_yyyy_date, company_name, num_shares, value, fee]
    return ' '.join(words)

def processSchwabCSV():
    with open(input_filename) as file:
        lines = file.readlines()
        lines = [line.rstrip().lstrip() for line in lines]

    supported_actions = ["Buy", "Sell", "Stock Split"]
    filtered_lines = []
    for line in lines:
        if (line[0:4] in ["Tran", "\"Tra", "\"Dat"]):
            # Hack to exclude the first two and last line put by Schwab.
            # Can do it more cleanly
            print("in here. line 0 4 is ", line[0:4])
            continue;

        chunks = [word.replace("\"", "") for word in line.split(',')]

        ################################
        ## IMPORTANT!! SKIPS FB STOCK ##
        ################################
        if (chunks[2] == "FB"):
            # don't handle FB stock
            continue;

        if (chunks[1] in ["Buy", "Sell"]):
            formatted_line = handleBuySellLine(chunks)
            filtered_lines.append(formatted_line)
            print("formatted line is ", formatted_line)

        if (chunks[1] == "Stock Split"):
            formatted_line = defineManualStockSplit(chunks)
            filtered_lines.append(formatted_line)
            print("formatted line is ", formatted_line)

        continue


    with open(output_filename, 'w') as output_file:
        for line in filtered_lines:
            output_file.write(line + '\n')

processSchwabCSV()
