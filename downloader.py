import logging
import requests
import shutil
import time
from pathlib import Path
from tqdm import tqdm
from datetime import datetime
from config import (DOWNLOAD_BASE_URL, FILES_TO_DOWNLOAD, REQUESTS_TIMEOUT,
                    RETRY_COUNT, RETRY_DELAY_SECONDS)

logger = logging.getLogger(__name__)

def _download_and_process_file(session: requests.Session, url: str, output_path: Path):
    try:
        with session.get(url, stream=True, timeout=REQUESTS_TIMEOUT) as r:
            r.raise_for_status()
            is_text_file = output_path.suffix.lower() == '.txt'
            """
                Because TC_*.txt files may be encoded in different formats,
                we handle them separately to ensure correct encoding. 
            """
            if is_text_file:
                content = r.text
                output_path.write_text(content, encoding='utf-8-sig')
                logger.debug("event=TextFileWriteSuccess file=%s", output_path.name)
                print(f"{output_path.name} is successfully downloaded.")
            else:
                """
                    Using tqdm to show a progress bar for binary files.
                """
                total_size = int(r.headers.get('content-length', 0))
                with tqdm.wrapattr(r.raw, "read", total=total_size, desc=output_path.name.ljust(35), leave=True) as raw_stream:
                    with output_path.open('wb') as f:
                        shutil.copyfileobj(raw_stream, f)
                logger.debug("event=BinaryFileWriteSuccess file=%s", output_path.name)
            return True, "Success"
    except requests.exceptions.RequestException as e:
        logger.warning("event=DownloadRequestFailed reason='%s' url=%s", e, url)
        return False, str(e)
    except Exception as e:
        logger.error("event=FileProcessingError reason='%s' path=%s", e, output_path, exc_info=True)
        return False, "File processing error"

def _handle_single_file_download(session: requests.Session, url: str, output_path: Path) -> str:
    """ 
        Handles the download of a single file, retrying if necessary.
        Returns 'downloaded' or 'failed' based on the outcome. 
    """
    for attempt in range(RETRY_COUNT):
        success, reason = _download_and_process_file(session, url, output_path)
        if success:
            logger.info("event=DownloadSuccess file=%s", output_path.name)
            return "downloaded"
        if attempt < RETRY_COUNT - 1:
            logger.warning("event=DownloadRetry file=%s attempt=%d reason='%s'", output_path.name, attempt + 1, reason)
            time.sleep(RETRY_DELAY_SECONDS)
    logger.error("event=DownloadFailure file=%s reason='Max retries reached'", output_path.name)
    return "failed"

def download_files_for_date(session: requests.Session, metadata: dict, root_dir: Path, force: bool) -> dict:
    """ 
        Downloads files for a specific date based on the 'key'. 
        It creates a directory for the date and downloads all dynamic files,
        skipping those that already exist if 'force' is False.
    """
    date_obj = datetime.strptime(metadata["Date"], "%d %b %Y")
    date_str_ymd = date_obj.strftime("%Y-%m-%d")
    date_for_filename = date_obj.strftime("%Y%m%d")
    key = metadata["key"]

    logger.info("event=ProcessDate date=%s key=%s", date_str_ymd, key)
    print(f"Downloading data for date: {date_str_ymd}")
    results = {'downloaded': [], 'skipped': [], 'failed': []}
    
    dynamic_files = [f for f in FILES_TO_DOWNLOAD if f['type'] == 'dynamic']

    for file_info in dynamic_files:
        local_filename = file_info['local_template'].format(date=date_for_filename)
        output_dir = root_dir / date_str_ymd
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / local_filename

        if not force and output_path.exists():
            results['skipped'].append(local_filename)
            continue
        
        url = DOWNLOAD_BASE_URL.format(key=key, filename=file_info['server_name'])
        status = _handle_single_file_download(session, url, output_path)
        results[status].append(local_filename)
            
    return results

def download_static_files(session: requests.Session, key: str, root_dir: Path, force: bool) -> dict:
    """ 
        Downloads static files that do not change with each date.These files 
        are typically structural and do not depend on the date. 
        It creates a directory for the date and downloads all static files,
        skipping those that already exist if 'force' is False.
    """

    logger.info("event=ProcessStaticFiles")
    print("Checking structural (static) files...")

    results = {'downloaded': [], 'skipped': [], 'failed': []}
    static_files = [f for f in FILES_TO_DOWNLOAD if f['type'] == 'static']

    for file_info in static_files:
        local_filename = file_info['local_template']
        output_path = root_dir / local_filename
        
        if not force and output_path.exists():
            results['skipped'].append(local_filename)
            continue
        
        url = DOWNLOAD_BASE_URL.format(key=key, filename=file_info['server_name'])
        status = _handle_single_file_download(session, url, output_path)
        results[status].append(local_filename)
    
    return results