from app import connector_config
from fastapi import Request, APIRouter, HTTPException, Query
import os
import httpx
from dotenv import load_dotenv


load_dotenv()

router = APIRouter(prefix="/infor", tags=["INFOR M3"])


@router.get("/inventory/by-order/{order_number}")
async def get_inventory_by_order(
    order_number: str,
    company: str,
    request: Request,
    warehouse: str,
    item_code: str,
    line_number: str | None = None,
    line_suffix: str | None = None,
    transaction_type: str | None = None,
    maxrecs: int = Query(default=20, ge=1, le=1000),
):
    """Return raw balance records for an order, item, and warehouse.

    Optional line and stock transaction type fields narrow the request.
    This endpoint is not a complete inventory export.
    """
    # Validate configuration before sending any network requests.
    base_url = setting("INFOR_BASE_URL").rstrip("/")
    client = request.app.state.client
    token = await get_infor_token(client)

    # cono selects the company; the uppercase fields are transaction inputs.
    params = {
        "cono": company,
        "RIDN": order_number,
        "WHLO": warehouse,
        "ITNO": item_code,
        "maxrecs": maxrecs,
    }
    for field, value in (("RIDL", line_number), ("RIDX", line_suffix),
                         ("TTYP", transaction_type)):
        if value is not None:
            params[field] = value

    response = await client.get(
        f"{base_url}/MMS060MI/LstBalIDByOrd",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params=params,
    )
    response.raise_for_status()
    return response.json()


# function to get the api token
def setting(name):
    """Read an Infor setting from the environment, then try connector_config.

    Return an error if the setting is missing, because Infor needs it to work.
    """
    value = os.getenv(name) or getattr(connector_config, name, None)
    if not value:
        raise HTTPException(503, f"Infor configuration missing: {name}")
    return value


async def get_infor_token(client):
    """Send the login details to Infor and return an access token.

    The other functions use this token to make authorised requests to Infor.
    """
    payload = {
        "grant_type": "password",
        "client_id": setting("INFOR_CLIENT_ID"),
        "client_secret": setting("INFOR_CLIENT_SECRET"),
        "username": setting("INFOR_USERNAME"),
        "password": setting("INFOR_PASSWORD"),
    }

    # Send the login details and wait for Infor's response.
    response = await client.post(
        setting("INFOR_TOKEN_URL"),
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    # Stop here if Infor returns an HTTP error.
    response.raise_for_status()
    # Read the token from the JSON response.
    return response.json()["access_token"]


@router.get("/purchase-orders/{puno}/lines")
async def get_purchase_order_lines(puno: str, request: Request):
    """Get the line items for a purchase order and return Infor's JSON response.

    puno is the purchase order number. Use the app's shared HTTP client and
    an access token to request its lines from Infor.
    """
    # Validate configuration before sending any network requests.
    base_url = setting("INFOR_BASE_URL").rstrip("/")
    client = request.app.state.client
    token = await get_infor_token(client)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    
    }

    url = f"{base_url}/PPS200MI/LstLine"

    response = await client.get(
        url,
        headers=headers, 
        params={"PUNO": puno}

    )

    response.raise_for_status()
    return response.json()

@router.get("/customer-orders/{orno}/lines")
async def get_customer_order_lines(orno: str, request: Request):
    """
    Get the line items for a customer order and return Infor's JSON response.

    orno is the customer order number.
    """
    # Validate configuration before sending any network requests.
    base_url = setting("INFOR_BASE_URL").rstrip("/")
    client = request.app.state.client
    token = await get_infor_token(client)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    url = f"{base_url}/OIS100MI/LstLine"

    response = await client.get(
        url,
        headers=headers,
        params={"ORNO": orno}
    )

    response.raise_for_status()
    return response.json()

async def fetch_order_lines(
    order_type: str,
    order_number: str,
    request: Request
):
    """
    Choose the purchase or customer order function for the ingestion process.

    Return the order lines, or turn connection problems and invalid responses
    into clear API errors.
    """
    try:
        if order_type == "purchase":
            return await get_purchase_order_lines(order_number, request)

        if order_type == "customer":
            return await get_customer_order_lines(order_number, request)

        raise HTTPException(
            status_code=422,
            detail="Order type must be purchase or customer."
        )

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Infor request timed out. Please retry."
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Infor request failed (HTTP {exc.response.status_code})."
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to connect to Infor."
        ) from exc

    except (ValueError, KeyError, AttributeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Infor returned an invalid response."
        ) from exc