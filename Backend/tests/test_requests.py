import requests
from app.connector_config import JIRA_BASE_URL

print("URL is:", repr(JIRA_BASE_URL))
try:
    print(requests.get(JIRA_BASE_URL + "/rest/api/3/myself", timeout=5).status_code)
except Exception as e:
    print(repr(e))
