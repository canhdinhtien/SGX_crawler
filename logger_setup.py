import logging
from logging.config import dictConfig

from pathlib import Path
import sys
from datetime import datetime

class JobIdFilter(logging.Filter):
    def __init__(self, job_id: str = "no-job-id"):
        super().__init__()
        self.job_id = job_id

    def filter(self, record):
        record.job_id = self.job_id
        return True

def setup_logging(log_dir: Path, job_id: str, debug_mode: bool = False):
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_filename = f"sgx_download_{datetime.now().strftime('%Y-%m-%d')}.log"
    log_file = log_dir / log_filename

    console_log_level = "DEBUG" if debug_mode else "WARNING"

    class ConsoleFormatter(logging.Formatter):
        def format(self, record):
            if record.levelno >= logging.WARNING:
                return f"[LỖI] {record.getMessage()}"
            return f"[{record.levelname}] {record.getMessage()}"

    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'console_clean': {
                '()': ConsoleFormatter,
            },
            'json': {
                '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
                'format': '%(asctime)s %(levelname)s %(name)s %(job_id)s %(message)s',
            },
        },
        'filters': {
            'job_id_filter': {
                '()': JobIdFilter,
                'job_id': job_id,
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': console_log_level,
                'formatter': 'console_clean',
                'stream': sys.stdout,
            },
            'rotating_json_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'DEBUG',
                'formatter': 'json',
                'filename': log_file,
                'maxBytes': 10 * 1024 * 1024,
                'backupCount': 5,
                'encoding': 'utf-8',
                'filters': ['job_id_filter'],
            },
        },
        'root': {
            'level': 'DEBUG',
            'handlers': ['console', 'rotating_json_file'],
        },
        'loggers': {
            'requests': {'level': 'WARNING', 'propagate': True},
            'urllib3': {'level': 'WARNING', 'propagate': True},
        }
    }
    
    dictConfig(logging_config)