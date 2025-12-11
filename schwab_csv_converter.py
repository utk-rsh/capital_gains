import collections
import datetime
import functools
from pprint import pprint

input_filename = "schwab_original.csv"
output_filename = "filtered_schwab.csv"
dividends_received_per_year = {
    "2019/20": 0,
    "2020/21": 0,
    "2021/22": 0,
    "2022/23": 0,
    "2023/24": 0,
    "2024/25": 0,
}
ignored_actions = set()


def convertSchwabActionToSupportedAction(action):
    if action == "Stock Split":
        return "SPLIT"
    return action.upper()


def defineManualStockSplit(chunks):
    mm_dd_yyyy_date = chunks[0][
        0:10
    ]  # taking first 10 chars (mm/dd/yyyy) as some activities have
    #  weird date formatting
    dd_mm_yyyy_date = datetime.datetime.strptime(mm_dd_yyyy_date, "%m/%d/%Y").strftime(
        "%d/%m/%Y"
    )
    company_name = chunks[2]

    output_line = dd_mm_yyyy_date + " " + company_name + " "
    if dd_mm_yyyy_date == "20/07/2021" and company_name == "NVDA":
        multiplier = "4"

    if dd_mm_yyyy_date == "31/08/2020" and company_name == "TSLA":
        multiplier = "5"

    if dd_mm_yyyy_date == "31/08/2020" and company_name == "AAPL":
        multiplier = "4"

    if dd_mm_yyyy_date == "18/07/2022" and company_name == "GOOGL":
        multiplier = "20"

    if dd_mm_yyyy_date == "29/06/2022" and company_name == "SHOP":
        multiplier = "10"

    if dd_mm_yyyy_date == "06/06/2022" and company_name == "AMZN":
        multiplier = "20"

    if dd_mm_yyyy_date == "10/06/2024" and company_name == "NVDA":
        multiplier = "10"

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
        chunks = [word.replace('"', "") for word in line.split(",")]
        date_chunks = [x for x in chunks[0].split("/")]
        month = date_chunks[0]
        year = date_chunks[1]
        gbp_usd_rate = chunks[1]
        year_month_rate_dict[year][month] = gbp_usd_rate

    return year_month_rate_dict


# get rate from dd/mm/yyyy date
def getGbpUsdRateFromDate(dd_mm_yyyy_date):
    gbp_usd_map = getGbpUsdConversionMap()
    chunks = dd_mm_yyyy_date.split("/")
    month = chunks[1]
    year = chunks[2]
    # print('month is ', month, ' and year is ', year)
    # print('map is ', gbp_usd_map)
    # print('date is ', dd_mm_yyyy_date)
    return float(gbp_usd_map[year][month])


def handleBuySellLine(chunks):
    mm_dd_yyyy_date = chunks[0][
        0:10
    ]  # taking first 10 chars (mm/dd/yyyy) as some activities have
    #  weird date formatting
    dd_mm_yyyy_date = datetime.datetime.strptime(mm_dd_yyyy_date, "%m/%d/%Y").strftime(
        "%d/%m/%Y"
    )
    action = convertSchwabActionToSupportedAction(chunks[1])
    company_name = chunks[2]
    num_shares = chunks[4]
    dollar_value = chunks[5].replace("$", "")
    gbp_usd_rate = getGbpUsdRateFromDate(dd_mm_yyyy_date)
    # "{:.2f}".format ensures that only 2 decimal points are printed
    value = "{:.2f}".format(
        float(chunks[5].replace("$", "")) * 1.0 / getGbpUsdRateFromDate(dd_mm_yyyy_date)
    )
    fee = "0"
    tax = "0"
    words = [action, dd_mm_yyyy_date, company_name, num_shares, value, fee]
    return " ".join(words)


# A dividend which is reinvested is equivalent to buying the stock. The amount of money being
# reinvested is dividend - NRA adj
def handleReinvestmentOfDividendAsBuy(chunks):
    chunks[1] = "Buy"
    return handleBuySellLine(chunks)


def financialYearFromMonthYear(dd_mm_yyyy_date: str):
    year = int(dd_mm_yyyy_date[-4:])
    month = int(dd_mm_yyyy_date[3:5])
    date = int(dd_mm_yyyy_date[0:2])
    if (month >= 5) or (date >= 6 and month == 4):  # Post April 5th
        return str(year) + "/" + str((year + 1) % 100)
    if (month <= 3) or (date <= 5 and month == 4):  # Pre April 5th, inclusive
        return str(year - 1) + "/" + str(year % 100)
    raise Exception("financial year calculation issue")


def trackDividendPerYear(chunks):
    mm_dd_yyyy_date = chunks[0][
        0:10
    ]  # taking first 10 chars (mm/dd/yyyy) as some activities have
    #  weird date formatting
    dd_mm_yyyy_date = datetime.datetime.strptime(mm_dd_yyyy_date, "%m/%d/%Y").strftime(
        "%d/%m/%Y"
    )
    fiscal_year = financialYearFromMonthYear(dd_mm_yyyy_date)
    if fiscal_year not in dividends_received_per_year:
        raise Exception(f"fiscal year not in dividend map. Year is {fiscal_year}")
    dividend_usd = float(chunks[7].replace("$", ""))
    gbp_usd_rate = getGbpUsdRateFromDate(dd_mm_yyyy_date)
    dividend_value = float("{:.2f}".format(dividend_usd / gbp_usd_rate))
    dividends_received_per_year[fiscal_year] += dividend_value
    return


def processSchwabCSV():
    with open(input_filename) as file:
        lines = file.readlines()
        lines = [line.rstrip().lstrip() for line in lines]

    filtered_lines = []
    for line in lines:
        print("line is ", line)
        if line[0:4] in ["Tran", '"Tra', '"Dat']:
            # Hack to exclude the first two and last line put by Schwab.
            # Can do it more cleanly
            print("in here. line 0 4 is ", line[0:4])
            continue

        chunks = [word.replace('"', "") for word in line.split(",")]
        month = int(chunks[0][0:2])  # taking first 2 chars (mm/dd/yyyy)
        year = int(chunks[0][6:10])  # taking 6th to 9th chars (mm/dd/yyyy)

        ################################
        ## IMPORTANT!! SKIPS FB STOCK ##
        ################################
        if chunks[2] == "FB" or chunks[2] == "META":
            # don't handle FB stock
            continue
        elif chunks[2] in ["SNAP", "ABNB", "LYFT", "TSLA"] and year <= 2023:
            # Because Schwab isn't giving me history before 2020 anymore, using this
            # as a way of ignoring all the buy and sells which had no impact to calculations
            # in 2023-24 year and beyond. As a result of this line, returns before the 23-24
            # year can no longer be trusted.
            print("Ignoring line of ", line)
            continue
        elif chunks[2] in ["PLTR"] and year <= 2021 and month <= 4:
            # Same as previous case, but handling PLTR separately because some disposal happened in 23-24.
            # Next year onwards, this can be consolidated into line above.
            print("Ignoring line of ", line)
            continue
        elif chunks[1] in ["Buy", "Sell"]:
            formatted_line = handleBuySellLine(chunks)
            filtered_lines.append(formatted_line)
            print("buy sell formatted line is ", formatted_line)
        elif chunks[1] == "Stock Split":
            formatted_line = defineManualStockSplit(chunks)
            filtered_lines.append(formatted_line)
            print("split formatted line is ", formatted_line)
        elif chunks[1] == "Reinvest Shares":
            formatted_line = handleReinvestmentOfDividendAsBuy(chunks)
            filtered_lines.append(formatted_line)
            print("dividend formatted line is ", formatted_line)
        elif (
            chunks[1] == "Qual Div Reinvest"
        ):  # When dividend being re-invested by equity
            trackDividendPerYear(chunks)
        elif (
            chunks[1] == "Qualified Dividend"
        ):  # When dividend not being re-invested by equity
            trackDividendPerYear(chunks)
        elif chunks[1] == "Cash Dividend":  # Cash dividend from ETF
            trackDividendPerYear(chunks)
        elif (
            chunks[1] == "Pr Yr Cash Div"
        ):  # Prior year cash dividend from ETF, same as dividend for UK
            trackDividendPerYear(chunks)
        elif (
            chunks[1] == "Pr Yr Special Div"
        ):  # Prior year cash dividend from ETF, same as dividend for UK
            trackDividendPerYear(chunks)
        else:
            ignored_actions.add(chunks[1])

    with open(output_filename, "w") as output_file:
        for line in filtered_lines:
            output_file.write(line + "\n")

    print("Dividends for each year are ")
    pprint(dividends_received_per_year)
    pprint("Ignored actions are ")
    pprint(ignored_actions)


processSchwabCSV()
