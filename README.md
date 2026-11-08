# Highland Beach Tide Explorer (2026)

A Streamlit dashboard using NOAA CO-OPS station **8722670 (Lake Worth Pier)** as an Atlantic-side proxy for Highland Beach, Florida.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

1. Upload `app.py` and `requirements.txt` to a GitHub repository.
2. Visit https://share.streamlit.io/ and sign in.
3. Choose **Create app**, select the repository, branch, and `app.py`.
4. Deploy. No NOAA API key or secrets are required.

## Details

- Retrieves monthly UTC hourly predictions and high/low events from NOAA's public API, plus boundary days to cover the complete 2026 Eastern-local calendar year.
- Converts UTC timestamps to America/New_York, handling daylight saving transitions correctly.
- Water heights are feet relative to **MLLW** (mean lower low water).
- Annual chart, daily chart with high/low events, monthly threshold analysis, and CSV export.
- Threshold counts are *hourly samples*, not exact continuous duration; do not use as a flood-risk determination.
- Predictions are astronomical only and do not include meteorological surge or wave runup.

API documentation: https://api.tidesandcurrents.noaa.gov/api/prod/

## Reliability and testing

- Retries transient NOAA errors (429 and 5xx).
- Rejects missing or irregular hourly timestamps before displaying analyses.
- Pins dependency versions tested on Python 3.12. Select Python 3.12 under Streamlit deployment advanced settings.
- Threshold totals count hourly samples, not exact hours of continuous exceedance.
- Run `python test_app.py` to check NOAA retrieval, all three views, year boundaries, daylight-saving dates, and threshold extremes. The first run makes 28 NOAA requests and may take several minutes.
