from pathlib import Path
from datetime import datetime

""" 
    Configuration for SGX Downloader
    This file contains constants and settings used throughout the application.
    It includes API URLs, file paths, and other parameters. 
"""
API_URL = "https://api3.sgx.com/infofeed/Apps?A=COW_Tickdownload_Content&B=TimeSalesData&C_T=20"
DOWNLOAD_BASE_URL = "https://links.sgx.com/1.0.0/derivatives-historical/{key}/{filename}"
DEFAULT_OUTPUT_DIR = Path("./derivatives_data")

FILES_TO_DOWNLOAD = [
    {'type': 'dynamic', 'server_name': 'WEBPXTICK_DT.zip', 'local_template': 'WEBPXTICK_DT-{date}.zip'},
    {'type': 'static',  'server_name': 'TickData_structure.dat', 'local_template': 'TickData_structure.dat'},
    {'type': 'dynamic', 'server_name': 'TC.txt', 'local_template': 'TC_{date}.txt'},
    {'type': 'static',  'server_name': 'TC_structure.dat', 'local_template': 'TC_structure.dat'}
]

REQUESTS_TIMEOUT = (10, 60)
RETRY_COUNT = 6
RETRY_DELAY_SECONDS = 30
HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Support download of data from 2015-08-03 onwards
MIN_DATE = datetime(2015, 8, 3)
BASE_DATE = (2015, 8, 3)

# Key for the BASE_DATE
BASE_KEY = 3369

# List of keys that are not available for download
MISSING_KEYS = [3590, 3591, 3710, 3711, 3712, 3848, 3849, 3874, 4239, 4766]

# Special Saturday that have keys
SPECIAL_SATURDAYS = {
    (2016, 1, 30): 3499, (2016, 6, 4): 3592, (2016, 9, 10): 3663,
    (2017, 2, 18): 3782, (2017, 6, 3): 3860, (2017, 9, 30): 3947,
    (2018, 3, 31): 4078, (2018, 12, 22): 4270, (2020, 2, 1): 4561,
    (2020, 11, 14): 4767
}

NORMALIZE_TEXT_ENCODING = "utf-8"