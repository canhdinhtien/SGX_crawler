import logging
from datetime import datetime, timedelta
from functools import lru_cache
from config import BASE_DATE, BASE_KEY, MISSING_KEYS, SPECIAL_SATURDAYS, MIN_DATE

logger = logging.getLogger(__name__)

_BASE_DATE_OBJ = datetime(*BASE_DATE)
_SPECIAL_SATURDAYS_OBJS = {datetime(*d): k for d, k in SPECIAL_SATURDAYS.items()}

def _is_trading_day(current_date: datetime) -> bool:
    return current_date.weekday() < 5

@lru_cache(maxsize=1024)
def find_key_for_date(target_date_str: str) -> dict | None:
    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d')
    except ValueError:
        logger.error("event=InvalidDateFormat date_str=%s", target_date_str)
        return None
    
    if target_date < MIN_DATE:
        return None

    logger.debug("event=HistoricalKeySearch date=%s", target_date_str)

    if target_date in _SPECIAL_SATURDAYS_OBJS:
        key = _SPECIAL_SATURDAYS_OBJS[target_date]
        return {"key": str(key), "Date": target_date.strftime("%d %b %Y")}
    
    if not _is_trading_day(target_date):
        return None

    """ 
        We can download data for any date if we have the key. So I define a function to calculate the 
        key based on the the base date, missing keys, and special Saturdays.
        Because the keys are normally sequential, and in a normal week, there are 5 keys (Monday to Friday).
        So we can estimate the key based on the number of weekdays since the base date. 
        Then, adjust for any missing keys and special Saturdays that fall within the range.
        If new missing keys and special Saturdays are added, the logic will not change. 
        Ensure that new missing keys added will not conflict with existing keys, and keep MISSING_KEYS is sorted.
    """
    diff = (target_date - _BASE_DATE_OBJ).days
    full_weeks, extra_days = diff // 7, diff % 7
    weekdays = full_weeks * 5
    for i in range(1, extra_days+1):
        day = (_BASE_DATE_OBJ.weekday() + i) % 7
        if day < 5:
            weekdays += 1
    est_key = BASE_KEY + weekdays
    for sat in _SPECIAL_SATURDAYS_OBJS:
        if _BASE_DATE_OBJ < sat <= target_date:
            est_key += 1
    for k in MISSING_KEYS:
        if BASE_KEY < k <= est_key:
            est_key += 1
    while est_key in MISSING_KEYS:
        est_key += 1
    return {"key": str(est_key), "Date": target_date.strftime("%d %b %Y")}