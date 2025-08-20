This project was developed by analyzing the underlying data API used by SGX’s derivatives page.

Why it works:
SGX uses predictable download URLs:
Files are stored at: https://links.sgx.com/1.0.0/derivatives-historical/{key}/{filename}
→ If we know the key and filename, we can download directly.

SGX exposes a hidden API:
This API returns the correct file list and key for the most recent trading day.
→ We use this as the source of truth to ensure correct and up-to-date downloads.

BY combining both methods, the tool ensures reliable and accurate data retrieval.

Features:
Download latest trading day (default)
Download last N trading days
Download specific date
Download date range

You can use commands: python main.py -h to explore all options:
