from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = ['https://www.googleapis.com/auth/drive.file']  # Allow upload

flow = InstalledAppFlow.from_client_secrets_file('client_id.json', SCOPES)
creds = flow.run_local_server(port=0)

# Save authorized user credentials including refresh_token
with open('token.json', 'w') as f:
    f.write(creds.to_json())

print("Authorized token saved to token.json")