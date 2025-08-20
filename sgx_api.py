import logging
import requests
import json
import time
from config import API_URL, REQUESTS_TIMEOUT, RETRY_COUNT, RETRY_DELAY_SECONDS

logger = logging.getLogger(__name__)

def fetch_api_metadata(session: requests.Session) -> list[dict]:
    """ 
    Get metadata from the SGX API: The SGX API provides derivatives data for 
    the 5 latest trading days, usually corresponding to weekdays 
    (Monday to Friday). Some times, the API may return less than 5 days of data.
    The API returns a JSON response containing a list of items, each with a 'key' and 'Date'.
    The 'key' is used to construct the download URL for the files.
    """
    for attempt in range(RETRY_COUNT):
        try:
            logger.debug("event=ApiRequestSent url=%s attempt=%d", API_URL, attempt + 1)
            response = session.get(API_URL, timeout=REQUESTS_TIMEOUT)
            response.raise_for_status()
            raw_data = response.json()

            if "items" not in raw_data or not isinstance(raw_data["items"], list):
                logger.error("event=ApiResponseInvalid reason='items key not found or not a list'")
                return []

            metadata = [{"key": item.get("key"), "Date": item.get("Date")}
                        for item in raw_data.get("items", [])
                        if isinstance(item, dict) and item.get("key") and item.get("Date")]
            
            logger.info("event=ApiFetchSuccess found_items=%d", len(metadata))
            return metadata
        
        except requests.exceptions.RequestException as e:
            logger.warning("event=ApiRequestFailed reason='%s' attempt=%d", e, attempt + 1)
            if attempt < RETRY_COUNT - 1:
                time.sleep(RETRY_DELAY_SECONDS)
        except json.JSONDecodeError as e:
            logger.error("event=ApiJsonError reason='%s' response_text='%.100s'", e, response.text)
            return []
    
    logger.error("event=ApiFetchFailure reason='Max retries reached'")
    return []