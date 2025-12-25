import collections
import datetime
import functools
from pprint import pprint

input_filename = "interactive_brokers_raw.csv"
output_filename = "filtered_ibkr.csv"

dividends_received_per_year = {
    "2019/20": 0,
    "2020/21": 0,
    "2021/22": 0,
    "2022/23": 0,
    "2023/24": 0,
    "2024/25": 0,
    "2025/26": 0,
}
ignored_actions = set()


def getGbpUsdConversionMap():
    """Output is a 2D dict of year -> month -> gbp to usd rate"""
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


def getGbpUsdRateFromDate(dd_mm_yyyy_date):
    """Get GBP/USD rate from dd/mm/yyyy date"""
    gbp_usd_map = getGbpUsdConversionMap()
    chunks = dd_mm_yyyy_date.split("/")
    month = chunks[1]
    year = chunks[2]
    return float(gbp_usd_map[year][month])


def financialYearFromMonthYear(dd_mm_yyyy_date: str):
    """Calculate UK fiscal year from date"""
    year = int(dd_mm_yyyy_date[-4:])
    month = int(dd_mm_yyyy_date[3:5])
    date = int(dd_mm_yyyy_date[0:2])
    if (month >= 5) or (date >= 6 and month == 4):  # Post April 5th
        return str(year) + "/" + str((year + 1) % 100)
    if (month <= 3) or (date <= 5 and month == 4):  # Pre April 5th, inclusive
        return str(year - 1) + "/" + str(year % 100)
    raise Exception("financial year calculation issue")


def convertYyyyMmDdToDbMmYyyy(yyyy_mm_dd_date):
    """Convert YYYY-MM-DD to DD/MM/YYYY"""
    return datetime.datetime.strptime(yyyy_mm_dd_date, "%Y-%m-%d").strftime("%d/%m/%Y")


def handleBuySellLine(chunks):
    """Process Buy/Sell transaction"""
    yyyy_mm_dd_date = chunks[2]
    dd_mm_yyyy_date = convertYyyyMmDdToDbMmYyyy(yyyy_mm_dd_date)
    action = chunks[5].upper()  # Transaction Type
    symbol = chunks[6]
    quantity = "{:.4f}".format(
        abs(float(chunks[7]))
    )  # Format quantity as positive number
    net_amount = chunks[11]  # Net Amount (includes commission) - always in USD
    quantity_float = abs(float(chunks[7]))

    # Calculate effective price per share (including commission) in GBP
    # We use Net Amount / Quantity instead of the Price field from CSV because
    # Net Amount already includes the commission, giving us the true cost per share
    # ASSUMPTION: Net Amount in CSV is always in USD (account base currency)
    gbp_usd_rate = getGbpUsdRateFromDate(dd_mm_yyyy_date)
    price = "{:.2f}".format(abs(float(net_amount)) / gbp_usd_rate / quantity_float)

    fee = "0"
    words = [action, dd_mm_yyyy_date, symbol, quantity, price, fee]
    return " ".join(words)


def trackDividendPerYear(chunks):
    """Track dividends per UK fiscal year"""
    yyyy_mm_dd_date = chunks[2]
    dd_mm_yyyy_date = convertYyyyMmDdToDbMmYyyy(yyyy_mm_dd_date)
    fiscal_year = financialYearFromMonthYear(dd_mm_yyyy_date)

    if fiscal_year not in dividends_received_per_year:
        raise Exception(f"fiscal year not in dividend map. Year is {fiscal_year}")

    symbol = chunks[6]
    net_amount = chunks[11]  # Net Amount - always in USD

    # Calculate dividend value in GBP
    # ASSUMPTION: Net Amount in CSV is always in USD (account base currency)
    gbp_usd_rate = getGbpUsdRateFromDate(dd_mm_yyyy_date)
    dividend_value = float("{:.2f}".format(abs(float(net_amount)) / gbp_usd_rate))

    dividends_received_per_year[fiscal_year] += dividend_value


def preprocessForexTradeLine(line):
    """
    Fix IBKR bug where forex trade amounts have commas in numbers
    Example: "Net Amount in Base from Forex Trade: 47,460 GBP.USD"
    The comma splits this incorrectly, so we need to remove it
    """
    if "Net Amount in Base from Forex Trade:" not in line:
        return line

    # Split by comma to check for the issue
    chunks = line.split(",")

    # Check if chunks[4] ends with a digit (indicating split number)
    if len(chunks) > 5 and chunks[4].strip() and chunks[4].strip()[-1].isdigit():
        # Check if chunks[5] contains pattern: digits followed by space followed by currencies
        next_chunk = chunks[5].strip()
        has_currency = any(curr in next_chunk for curr in ["GBP", "EUR", "USD"])
        # Check if it starts with digits followed by space
        starts_with_digit_space = len(next_chunk) > 0 and next_chunk[0].isdigit() and ' ' in next_chunk

        if has_currency and starts_with_digit_space:
            # Merge chunks[4] and chunks[5] by removing the comma between them
            chunks[4] = chunks[4] + chunks[5]
            # Remove the now-merged chunks[5]
            chunks.pop(5)
            # Rejoin the line
            return ",".join(chunks)

    return line


def processIBKRCSV():
    """Main processing function"""
    with open(input_filename) as file:
        lines = file.readlines()
        lines = [line.rstrip().lstrip() for line in lines]

    # Print key assumptions
    print("=" * 60)
    print("KEY ASSUMPTION:")
    print("Net Amount in IBKR CSV is always in USD (account base currency)")
    print("All values will be converted from USD to GBP using exchange rates")
    print("=" * 60)
    print()

    filtered_lines = []
    skipped_header_lines = []

    for line in lines:
        # Preprocess forex trade lines to fix comma issue
        line = preprocessForexTradeLine(line)

        # Skip header lines (first 9 lines)
        if not line.startswith("Transaction History,Data,"):
            skipped_header_lines.append(line)
            continue

        chunks = [word.replace('"', "") for word in line.split(",")]

        # Extract transaction type
        transaction_type = chunks[5]
        symbol = chunks[6] if len(chunks) > 6 else ""

        # Check for stock splits - throw error if found
        if "split" in transaction_type.lower() or "Stock Split" in transaction_type:
            raise Exception(f"Stock split detected! Please handle manually: {line}")

        # Handle Buy/Sell transactions
        if transaction_type in ["Buy", "Sell"]:
            if not symbol:
                raise Exception(f"Symbol is empty for Buy/Sell transaction: {line}")
            formatted_line = handleBuySellLine(chunks)
            filtered_lines.append(formatted_line)
            print(f"{transaction_type} formatted line: {formatted_line}")

        # Handle Dividends
        elif transaction_type == "Dividend":
            trackDividendPerYear(chunks)

        # Ignore other transaction types
        else:
            if transaction_type:  # Add transaction type to ignored actions
                ignored_actions.add(transaction_type)

    # Write output file
    with open(output_filename, "w") as output_file:
        for line in filtered_lines:
            output_file.write(line + "\n")

    print()
    print("=" * 60)
    print("Skipped header/non-transaction lines:")
    for line in skipped_header_lines:
        print(f"  {line}")
    print("=" * 60)
    print()
    print("=" * 60)
    print("Dividends for each year (in GBP):")
    pprint(dividends_received_per_year)
    print()
    print("Ignored actions:")
    pprint(ignored_actions)
    print("=" * 60)


processIBKRCSV()
