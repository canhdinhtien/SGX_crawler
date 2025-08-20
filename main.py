import argparse
import logging
import requests
import sys
from datetime import datetime, timedelta
from pathlib import Path
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger

try:
    from functools import cached_property
except ImportError:
    class cached_property:
        def __init__(self, func):
            self.func = func
        def __get__(self, instance, owner):
            if instance is None: return self
            value = instance.__dict__[self.func.__name__] = self.func(instance)
            return value

from config import DEFAULT_OUTPUT_DIR, HTTP_HEADERS, MIN_DATE
from sgx_api import fetch_api_metadata
from downloader import download_files_for_date, download_static_files
from historical_finder import find_key_for_date

logger = logging.getLogger()

class LatestTradingDayFetcher:
    def __init__(self):
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(HTTP_HEADERS)
        return self._session

    @cached_property
    def latest_day(self) -> datetime.date:
        metadata = fetch_api_metadata(self.session)
        latest_date_str = metadata[0]['Date']
        return datetime.strptime(latest_date_str, "%d %b %Y").date()

latest_day_fetcher = LatestTradingDayFetcher()

class JobIdFilter(logging.Filter):
    def __init__(self, job_id: str = "no-job-id"):
        super().__init__()
        self.job_id = job_id

    def filter(self, record):
        record.job_id = self.job_id
        return True

class ConsoleFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno >= logging.WARNING:
            return f"[ERROR] {record.getMessage()}"
        return f"[{record.levelname}] {record.getMessage()}"

def setup_logging(log_file: Path, job_id: str, debug_mode: bool = False):
    console_log_level = "DEBUG" if debug_mode else "WARNING"
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    logger.setLevel(logging.DEBUG)
    
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    json_formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(job_id)s %(message)s'
    )
    file_handler.setFormatter(json_formatter)
    file_handler.addFilter(JobIdFilter(job_id))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_log_level)
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)

    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

class SgxDownloader:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.output_dir = Path(args.output_dir)
        self.session = self._create_session()
        self._api_cache = None

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(HTTP_HEADERS)
        return session

    def _get_api_metadata(self) -> list[dict]:
        if self._api_cache is None:
            logger.info("event=ApiCallTriggered")
            self._api_cache = fetch_api_metadata(self.session)
        return self._api_cache

    def run(self):
        logger.info("event=JobStart args=%s", vars(self.args))
        try:
            start_date, end_date = self._determine_date_range()
            targets = self._gather_targets(start_date, end_date)
        except ValueError as e:
            logger.critical("event=ConfigError reason='%s'", e)
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)
        if not targets:
            logger.info("event=JobEnd reason='No target dates found'")
            print("Don't find any data matching the request.")
            return
        if not self.args.force and sys.stdout.isatty():
            existing_dates = self._find_existing_dates(targets)
            if existing_dates:
                should_continue = self._handle_interactive_choice(existing_dates)
                if not should_continue:
                    logger.info("event=JobEnd reason='User cancelled'")
                    return
        self._process_downloads(targets)
        logger.info("event=JobEnd status=success")

    def _gather_targets(self, start_date, end_date) -> list[dict]:
        """ 
            Gathers target dates for downloading files.
            It checks the API for the latest data and falls back to historical key finding if necessary. 
        """
        logger.info("event=TargetGathering start_date=%s end_date=%s",
                    start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        api_map = {}
        if end_date >= (datetime.now().date() - timedelta(days=10)):
            api_data = self._get_api_metadata()
            api_map = {item['Date']: item for item in api_data}
        else:
            logger.info("event=ApiCallSkipped reason='SGX API data is too old'")
        targets = []
        current_date = start_date
        print(f"[!] PLEASE NOTE THAT THE DATES WITHOUT DATA MAY NOT BE TRANSACTION DAYS OR DATA IS NOT AVAILABLE YET.\n \
   DATES WITHOUT DATA WILL BE SKIPPED. \n")
        while current_date <= end_date:
            date_str_api = current_date.strftime("%d %b %Y")
            date_str_ymd = current_date.strftime("%Y-%m-%d")
            metadata = api_map.get(date_str_api) or find_key_for_date(date_str_ymd)
            if metadata:
                targets.append(metadata)
            current_date += timedelta(days=1)
        logger.info("event=TargetsGathered count=%d", len(targets))
        return targets

    def _determine_date_range(self):
        """ 
            Determines the date range for downloading data based on user input or API data.
            It returns a tuple of start and end dates. 
            If no specific date is provided, it defaults to the latest available date from the API.
            If no dates are specified, but user wants to download n-last days, it calculates the range based on the latest available date.
            If a specific date is provided, it validates the date and returns it as both start and end date.
            If a date range is specified, it validates the dates and ensures they are within the available data range.
        """
        latest_date = latest_day_fetcher.latest_day
        today = datetime.now().date()
        if not any([self.args.date, self.args.days, self.args.start_date]):
            api_metadata = self._get_api_metadata()
            if not api_metadata: raise ValueError("Cannot find any data from API.")
            latest_date = datetime.strptime(api_metadata[0]['Date'], "%d %b %Y").date()
            return latest_date, latest_date
        if self.args.date:
            start = datetime.strptime(self.args.date, "%Y-%m-%d").date()
            return start, start
        if self.args.days:
            if today > latest_date:
                delta = today - latest_date
                end = latest_date
                start = end - timedelta(days=self.args.days - delta.days)
                return start, end
            end = today
            start = end - timedelta(days=self.args.days - 1)
            return start, end
        if self.args.start_date:
            start = datetime.strptime(self.args.start_date, "%Y-%m-%d").date()
            end_date_str = self.args.end_date or latest_date.strftime("%Y-%m-%d")
            end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if start > end:
                raise ValueError("Start date cannot be after end date.")
            return start, end
        raise ValueError("Invalid date parameter combination.")

    def _process_downloads(self, targets: list[dict]):
        targets.sort(key=lambda x: datetime.strptime(x['Date'], "%d %b %Y"), reverse=True)
        logger.info("event=DownloadPhaseStart total_days=%d force_mode=%s", len(targets), self.args.force)

        all_results = {'downloaded': [], 'skipped': [], 'failed': []}

        first_day_key = targets[0]['key'] 
        static_results = download_static_files(self.session, first_day_key, self.output_dir, self.args.force)
        for key in all_results:
            all_results[key].extend(static_results[key])

        for item in targets:
            daily_results = download_files_for_date(self.session, item, self.output_dir, self.args.force)
            for key in all_results:
                all_results[key].extend(daily_results.get(key, []))

        print("\n" + "-" * 50)
        print("Report for download phase:")
        print("-" * 50)

        if all_results['downloaded']:
            print(f"\n[ DOWNLOADED FILES ({len(all_results['downloaded'])}) ]")
            for filename in sorted(all_results['downloaded']):
                print(f"  - {filename}")
        
        if all_results['skipped']:
            print(f"\n[ SKIPPED FILES ({len(all_results['skipped'])}) ]")
            for filename in sorted(all_results['skipped']):
                print(f"  - {filename} (File already exists.)")
        
        if all_results['failed']:
            print(f"\n[ FAILED FILES ({len(all_results['failed'])}) ]")
            for filename in sorted(all_results['failed']):
                print(f"  - {filename}")
        
        print("\nFINISH.")
        logger.info("event=DownloadPhaseEnd summary=%s", {k: len(v) for k, v in all_results.items()})

    def _find_existing_dates(self, targets: list[dict]) -> list[str]:
        """        
            Checks for existing data in the output directory for the given targets.
            Returns a list of date strings for which data already exists. 
        """
        existing = []
        for item in targets:
            date_obj = datetime.strptime(item["Date"], "%d %b %Y")
            date_str_ymd = date_obj.strftime("%Y-%m-%d")
            date_folder = self.output_dir / date_str_ymd
            if date_folder.exists() and any(date_folder.iterdir()):
                existing.append(date_str_ymd)
        return existing

    def _handle_interactive_choice(self, existing_dates: list[str]) -> bool:
        print("-" * 50)
        print(f"!Found existing data for {len(existing_dates)} date(s).")
        for date_str in existing_dates[:5]: print(f"    - {date_str}")
        if len(existing_dates) > 5: print(f"    - and {len(existing_dates) - 5} other dates...")
        try:
            choice = input("""
SELECT AN ACTION:
  [1] Continue (Skip existing files).
  [2] Redownload all file (Overwrite).
  [Other] Cancel.

Choose (1/2): """).strip()
            if choice == '1': logger.info("event=UserConfirm action=continue_skip"); return True
            if choice == '2': logger.info("event=UserConfirm action=force_redownload"); self.args.force = True; return True
            logger.info("event=UserConfirm action=cancel"); return False
        except (EOFError, KeyboardInterrupt):
            print("\n-> CANCEL."); logger.info("event=JobCancel reason='User interrupted'"); return False

def create_arg_parser() -> argparse.ArgumentParser:
    """
        If no specific date is provided, it defaults to the latest available date from the API.
        If want to download specific date, use -d/--date option.
        If want to download n-last dates, use -n/--days option.
        If want to download data from a specific date range, use -s/--start-date and -e/--end-date options.
        If no -e/--end-date is provided, it defaults to today.
        If -e/--end-date is provided, it must be used with -s/--start-date.
        If -f/--force is specified, it forces redownload of existing data.
        If --debug is specified, it enables logging at DEBUG level to console.
        If -h/--help is specified, it displays this help message.
        If -o/--output-dir is specified, it sets the data storage directory.
        If no -o/--output-dir is specified, it defaults to the value from config.py (DEFAULT_OUTPUT_DIR).
    """
    parser = argparse.ArgumentParser(description="Daily derivatives data download tool from SGX.", formatter_class=argparse.RawTextHelpFormatter, add_help=False)
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("-d", "--date", type=str, help="Download for a specific day (YYYY-MM-DD).")
    group.add_argument("-n", "--days", type=int, help="Download for the last N days.")
    group.add_argument("-s", "--start-date", type=str, help="Start day (YYYY-MM-DD).")
    parser.add_argument("-e", "--end-date", type=str, help="End day (YYYY-MM-DD), only use with --start-date.")
    parser.add_argument("-o", "--output-dir", default=str(DEFAULT_OUTPUT_DIR), help=f"Data storage directory.")
    parser.add_argument("-f", "--force", action="store_true", help="Force redownload of existing data.")
    parser.add_argument("--debug", action="store_true", help="Enable logging at DEBUG level to console.")
    parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS, help="Display this help message.")
    def valid_date(s: str):
        try:
            d = datetime.strptime(s, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise argparse.ArgumentTypeError(f"\n[!] Invalid date '{s}'. Please use the YYYY-MM-DD format for a valid, existing date.")
        
        latest_day = latest_day_fetcher.latest_day

        if d > latest_day:
            raise argparse.ArgumentTypeError(f"\n[!] No data available for date {s}. Please select a date on or before {latest_day} (the most recent date with data).")
        if d < MIN_DATE.date():
            raise argparse.ArgumentTypeError(f"\n[!] Dates before {MIN_DATE.strftime('%Y-%m-%d')} are not supported.")
        return s
    for action in parser._actions:
        if action.dest in ['date', 'start_date', 'end_date']:
            action.type = valid_date
    return parser

if __name__ == "__main__":
    job_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    parser = create_arg_parser()
    
    log_dir = Path(DEFAULT_OUTPUT_DIR) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"sgx_download_{datetime.now().strftime('%Y-%m-%d')}.log"
    
    pre_init_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    pre_init_handler.setLevel(logging.DEBUG)
    json_formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(job_id)s %(message)s'
    )
    pre_init_handler.setFormatter(json_formatter)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(pre_init_handler)
    logger.addFilter(JobIdFilter(job_id))

    args = None
    try:
        args = parser.parse_args()
    except SystemExit as e:
        if e.code == 0: sys.exit(0)
        logger.error(f"ArgumentParser exited with error code {e.code}.", extra={"event": "ArgParseError"})
        sys.exit(e.code)

    setup_logging(log_file, job_id, args.debug)

    if args.end_date and not args.start_date:
        err_msg = "--end-date requires --start-date to be specified."
        logger.error(err_msg)
        print(err_msg, file=sys.stderr)
        sys.exit(2)

    try:
        downloader = SgxDownloader(args)
        downloader.run()
    except Exception as e:
        logger.critical("event=JobFailed reason='%s'", e, exc_info=True)
        print(f"\n[FATAL ERROR] An unexpected error has occurred. Please refer to the log file for more details.", file=sys.stderr)
        sys.exit(1)