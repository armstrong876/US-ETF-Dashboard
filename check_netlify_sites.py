import requests

token = "nfp_8f2UiPxVQUbcTNbxGU8GqdbAVDLf2jnd6936"
headers = {"Authorization": f"Bearer {token}"}

response = requests.get("https://api.netlify.com/api/v1/sites", headers=headers)
if response.status_code == 200:
    sites = response.json()
    for site in sites:
        print(f"Name: {site['name']}, ID: {site['id']}, URL: {site['url']}")
else:
    print(f"Error: {response.status_code} - {response.text}")
