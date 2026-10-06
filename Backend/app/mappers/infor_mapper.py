"""
The Connector receives raw order lines and item master data.
The Mapper should receive that response and convert it into a consistent structure.

The mapper’s responsibilities are to:
- Extract the order records from the API response.
- Rename source fields into clear, consistent names.
- Convert quantities and dates into agreed formats.
- Preserve identifiers as strings, including leading zeros.
- Keep missing values visible and retain the original record.
- Build stable IDs using enough context to distinguish clients, companies, orders, and lines.
"""

from datetime import datetime
from math import isfinite
from urllib.parse import quote


# Check Infor Errors and extracts records from results
def extract_infor_records(payload: dict):
    # Infor API connector passes the response to this function 'payload'

    if type(payload) is dict:
        results = payload.get("results")
        if not isinstance(results, list):
            raise ValueError("Infor results must be a list.")
        failed_transactions = payload.get("nrOfFailedTransactions", 0)
        try:
            failed_transactions = int(failed_transactions)
        except (TypeError, ValueError):
            raise ValueError("Invalid nrOfFailedTransactions value")
        if failed_transactions > 0:
            raise ValueError("Record does not exist")

    else:
        raise ValueError("Infor Response must be a dictionary")

    records = []

    # Looping through the infor results and collecting each one
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Each transaction result must be a dictionary.")

        # Use the actual error message returned by Infor.
        if result.get("errorMessage"):
            raise ValueError(result["errorMessage"])

        batch = result.get("records")
        if not isinstance(batch, list):
            raise ValueError("Transaction records must be a list.")

        for record in batch:
            if not isinstance(record, dict):
                raise ValueError("Each record must be a dictionary.")

        records.extend(batch)

    return records


# transforms purchase order line into a standard format.
def map_purchase_order_line(record, tenant, order_number):
    line_number = record.get("PNLI")
    line_suffix = record.get("PNLS")

    # All parts are needed to reliably identify this order line.
    id_parts = [
        "infor_m3",
        tenant,
        "purchase",
        order_number,
        line_number,
        line_suffix,
    ]

    if any(part is None or str(part).strip() == "" for part in id_parts):
        raise ValueError("Cannot create document ID: missing order identifiers.")

    document_id = ":".join(str(part).strip() for part in id_parts)
    # Copy values into clearly named fields without changing the raw record.
    quantities = {}

    for field in ("ORQA", "RVQA", "IVQA"):
        value = record.get(field)

        if value is None or (isinstance(value, str) and not value.strip()):
            quantities[field] = None
        else:
            try:
                quantities[field] = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid quantity for {field}: {value!r}")

    mapped_record = {
        "source": "infor_m3",
        "tenant": tenant,
        "order_type": "purchase",
        "order_number": order_number,
        "line_number": record.get("PNLI"),
        "line_suffix": record.get("PNLS"),
        "item_code": record.get("ITNO"),
        "ordered_quantity": quantities["ORQA"],
        "received_quantity": quantities["RVQA"],
        "invoiced_quantity": quantities["IVQA"],
        "content": record.copy(),
        "document_id": document_id,  # adding document id, for later recognition if needed
    }

    return mapped_record


# transforms customer order line into standard format.
def map_customer_order_line(record, tenant, order_number):
    line_number = record.get("PONR")
    line_suffix = record.get("POSX")

    # All parts are needed to reliably identify this order line.
    id_parts = [
        "infor_m3",
        tenant,
        "customer",
        order_number,
        line_number,
        line_suffix,
    ]

    if any(part is None or str(part).strip() == "" for part in id_parts):
        raise ValueError("Cannot create document ID: missing order identifiers.")

    document_id = ":".join(str(part).strip() for part in id_parts)
    # Copy values into clearly named fields without changing the raw record.
    quantities = {}

    for field in ("ORQT", "DLQT", "IVQT"):
        value = record.get(field)

        if value is None or (isinstance(value, str) and not value.strip()):
            quantities[field] = None
        else:
            try:
                quantities[field] = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid quantity for {field}: {value!r}")

    mapped_record = {
        "source": "infor_m3",
        "tenant": tenant,
        "order_type": "customer",
        "order_number": order_number,
        "line_number": line_number,
        "line_suffix": line_suffix,
        "item_code": record.get("ITNO"),
        "ordered_quantity": quantities["ORQT"],
        "delivered_quantity": quantities["DLQT"],
        "invoiced_quantity": quantities["IVQT"],
        "content": record.copy(),
        "document_id": document_id,
    }

    return mapped_record


"""
    Convert one raw item dictionary into a standardised item dictionary.
    The caller supplies the tenant and company used to fetch the item.
"""


def map_item_master_record(record, tenant, company):
    if not isinstance(record, dict):
        raise ValueError("Item record must be a dictionary.")

    item_code = record.get("ITNO")

    # These identifiers are needed to recognise the same item on later runs.
    for value in (tenant, company, item_code):
        if value is None or str(value).strip() == "":
            raise ValueError(
                "Cannot create item ID: missing tenant, company, or item code."
            )

    # Keep identifiers as text so leading zeros are preserved.
    tenant = str(tenant).strip()
    company = str(company).strip()
    item_code = str(item_code).strip()
    document_id = f"infor_m3:{tenant}:{company}:item:{item_code}"

    # Convert a date such as 20100312 into 2010-03-12.
    # A missing date stays None; do not invent a date or time zone.
    modified_date = None
    raw_date = record.get("LMDT")
    if raw_date is not None and str(raw_date).strip() != "":
        date_text = str(raw_date).strip()
        if len(date_text) != 8 or not date_text.isdigit():
            raise ValueError(f"Invalid item modified date: {raw_date!r}")
        try:
            modified_date = datetime.strptime(date_text, "%Y%m%d").date().isoformat()
        except ValueError:
            raise ValueError(f"Invalid item modified date: {raw_date!r}")

    # Rename the fields and retain the original data for checking later.
    mapped_record = {
        "source": "infor_m3",
        "record_type": "item",
        "tenant": tenant,
        "company": company,
        "document_id": document_id,
        "item_code": item_code,
        "item_name": record.get("ITDS"),
        "description": record.get("FUDS"),
        # Keep the source code until the business rules define its meaning.
        "status_code": record.get("STAT"),
        "unit_of_measure": record.get("UNMS"),
        "item_group": record.get("ITGR"),
        "item_type": record.get("ITTY"),
        "modified_date": modified_date,
        "content": record.copy(),
    }
    return mapped_record


def map_inventory_record(record, tenant, company):
    """Standardise one stock balance record using the request's tenant and company."""
    if not isinstance(record, dict):
        raise ValueError("Inventory record must be a dictionary.")

    # Keep the stock identity separate from the order used to look it up.
    identifiers = {
        "tenant": tenant,
        "company": company,
        "item_code": record.get("ITNO"),
        "warehouse_code": record.get("WHLO"),
        "location_code": record.get("WHSL"),
    }
    for name, value in identifiers.items():
        if value is None or str(value).strip() == "":
            raise ValueError(f"Missing inventory identifier: {name}")
        identifiers[name] = str(value).strip()

    # Reject a company mismatch rather than label stock with the wrong company.
    source_company = record.get("CONO")
    if (
        source_company is not None
        and str(source_company).strip() != identifiers["company"]
    ):
        raise ValueError("Inventory company does not match the requested company.")

    # Lot and container may be blank, but must be present to identify the balance.
    for field, name in (
        ("BANO", "lot_number"),
        ("CAMU", "container"),
        ("REPN", "receiving_number"),
    ):
        if field not in record or record[field] is None:
            raise ValueError(f"Missing inventory identity field: {field}")
        identifiers[name] = str(record[field]).strip()

    # Escape separators so different stock identities cannot share an ID.
    id_parts = [
        identifiers["tenant"],
        identifiers["company"],
        "inventory",
        identifiers["item_code"],
        identifiers["warehouse_code"],
        identifiers["location_code"],
        identifiers["lot_number"],
        identifiers["container"],
        identifiers["receiving_number"],
    ]
    document_id = "infor_m3:" + ":".join(quote(part, safe="") for part in id_parts)

    # Missing quantities stay None. Zero means a known quantity of zero.
    quantities = {}
    for field in ("STQT", "ALQT", "MVB1", "MVB2"):
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            quantities[field] = None
        else:
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid inventory quantity for {field}: {value!r}")
            if isinstance(value, bool) or not isfinite(number):
                raise ValueError(f"Invalid inventory quantity for {field}: {value!r}")
            quantities[field] = number

    mapped_record = {
        "source": "infor_m3",
        "record_type": "inventory",
        "document_id": document_id,
        **identifiers,
        "item_name": record.get("ITDS"),
        "unit_of_measure": record.get("UNMS"),
        "balance_status_code": record.get("STAS"),
        "approved_on_hand_quantity": quantities["STQT"],
        "allocated_quantity": quantities["ALQT"],
        # These are distinct Infor measures, not total warehouse availability.
        "movable_net_1": quantities["MVB1"],
        "movable_net_2": quantities["MVB2"],
        "content": record.copy(),
    }
    return mapped_record


def map_inventory_response(payload, tenant, company):
    """Extract and map the balance records in one inventory API response.

    This maps only the returned batch; it does not fetch additional pages.
    """
    records = extract_infor_records(payload)
    if payload.get("wasTerminated"):
        raise ValueError(
            "Infor terminated the inventory response; it may be incomplete."
        )
    mapped_records = []
    for record in records:
        mapped_records.append(map_inventory_record(record, tenant, company))
    return mapped_records


def map_item_master_response(payload, tenant, company):
    """Extract items from an Infor response and return a list of mapped items."""
    records = extract_infor_records(payload)
    mapped_records = []

    # Map each item separately, using the same tenant and company.
    for record in records:
        mapped_record = map_item_master_record(record, tenant, company)
        mapped_records.append(mapped_record)

    return mapped_records


# Extracts records and call the correct mapper for each line.
def map_infor_response(payload, order_type, tenant, order_number):
    records = extract_infor_records(payload)
    mapped_records = []
    # for each record:
    for record in records:
        if order_type == "purchase":
            mapped_record = map_purchase_order_line(record, tenant, order_number)

        else:
            mapped_record = map_customer_order_line(record, tenant, order_number)

        mapped_records.append(mapped_record)

    # return mapped records
    return mapped_records
