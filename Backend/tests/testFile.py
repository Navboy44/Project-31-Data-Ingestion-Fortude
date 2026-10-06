import requests
import json

from app.mappers.jira_mapper import map_jira_response_to_canonical
from app.mappers.jira_transformer import transform_canonical_tickets_for_l3


def test_my_jira_endpoint():
    field_url = "http://127.0.0.1:8000/jira/get_fields"
    issue_url = "http://127.0.0.1:8000/jira/my_issues"
    authentication_url = "http://127.0.0.1:8000/jira/authentication_check"

    print(f"Testing endpoint: {authentication_url}...")
    try:
       
        response = requests.get(authentication_url)
        
        # Check if the FastAPI backend returned a success
        if response.status_code == 200:
            authen_data = response.json()
            
            print("Successfully verify auth info!")
        else:
            print(f"Failed! Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the FastAPI server.")
    try:
       
        response = requests.get(field_url)
        
        # Check if the FastAPI backend returned a success
        if response.status_code == 200:
            field_data = response.json()
            
            print("Successfully retrieve field data!")
        else:
            print(f"Failed! Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("Error: Could not fetch field data")

    try:
       
        response = requests.get(issue_url)
        
        # Check if the FastAPI backend returned a success
        if response.status_code == 200:
            data = response.json()
            issues = data.get("issues", [])

            print("Successfully connected to FastAPI!")
            print(f"Found {len(issues)} unfinished issues assigned to you.\n")
            for issue in issues:
                
                print(f" - {issue['key']}: {issue['fields']['summary']} - {issue['fields']['issuetype']['name']}")

            if len(issues) > 0:
                canonical_tickets = map_jira_response_to_canonical(data)
                transformed_tickets = transform_canonical_tickets_for_l3(canonical_tickets)

                print("\n--- All canonical tickets ---")
                for ticket in canonical_tickets:
                    print(json.dumps(ticket, indent=2))

                print("\n--- All transformed L3 tickets ---")
                for ticket in transformed_tickets:
                    print(json.dumps(ticket, indent=2))

        else:
            print(f"Failed! Status Code: {response.status_code}")
            print(f"Response: {response.text}")

    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the FastAPI server. Is it running?")


if __name__ == "__main__":
    test_my_jira_endpoint()