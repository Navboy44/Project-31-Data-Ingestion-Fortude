# Infor order ingestion

In New Data Ingestion, select **Infor Sales**, a mapper and rule, then choose **Customer order** or **Purchase order** and enter an order number. Start fetches that order's lines once, preserves the original M3 fields in each document's `content`, applies the selected rule, and saves `backend/local_data/output/infor_<type>_<number>.json`. Re-running the same order replaces its JSON snapshot. History records the line count and Local JSON destination.

This integration uses a fixed Infor mapper. The mapper dropdown does not select a different implementation. Local JSON is the supported output for Infor; database and Kafka delivery are not implemented here.

Set these environment variables on the backend (or in its `.env` file):

- `INFOR_TOKEN_URL`: OAuth token endpoint
- `INFOR_BASE_URL`: M3 MI base URL, before `/PPS200MI/LstLine` or `/OIS100MI/LstLine`
- `INFOR_CLIENT_ID`
- `INFOR_CLIENT_SECRET`
- `INFOR_USERNAME`
- `INFOR_PASSWORD`

Authentication retains the connector's existing password grant. Credentials remain on the backend. Missing settings produce a configuration error in the ingestion form.

Raw-data routes are also available at `/infor/purchase-orders/{puno}/lines` and `/infor/customer-orders/{orno}/lines`. Ingestion reuses these existing route functions through a small dispatcher. The backend lifespan creates and closes the shared HTTP client used by `request.app.state.client`.

Expected responses contain `results[].records[]` (or top-level `records`). Transaction errors and malformed responses fail ingestion; an empty records list succeeds with zero lines. Live verification requires configured Infor credentials and a known order number.

Run focused tests from the repository root:

```sh
PYTHONPATH=backend/app:. python -m pytest backend/tests/test_infor_ingestion.py backend/tests/test_main_ingestion.py -q
```
