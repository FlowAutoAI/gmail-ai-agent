import os.path
import base64
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# SCOPES now includes "compose" to allow drafting
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose"
]

def search_emails(service, query):
    """Searches for emails matching the query."""
    try:
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        
        if not messages:
            print("No emails found matching criteria.")
            return None
        
        return messages
    except HttpError as error:
        print(f"An error occurred during search: {error}")
        return None

def create_draft(service, user_id, thread_id, original_subject):
    """Creates a draft reply."""
    try:
        message = EmailMessage()
        message.set_content("Hi,\n\nThanks for reaching out about the BrickIntel Investment Tool.\n\nI'd be happy to schedule a one-on-one session next Tuesday to get you set up.\n\nBest,\nJenica~BridgesBricks")
        
        if not original_subject.startswith("Re:"):
            message["Subject"] = f"Re: {original_subject}"
        else:
            message["Subject"] = original_subject

        message["To"] = "recipient@example.com"
        message["From"] = user_id
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        create_message = {
            'message': {
                'raw': encoded_message,
                'threadId': thread_id
            }
        }
        
        draft = service.users().drafts().create(userId=user_id, body=create_message).execute()
        print(f"SUCCESS! Draft created. ID: {draft['id']}")
        return draft

    except HttpError as error:
        print(f"An error occurred creating draft: {error}")
        return None

def main():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("gmail", "v1", credentials=creds)

        # Search for the specific BrickIntel email
        print("Searching for BrickIntel inquiries...")
        query = 'subject:BrickIntel OR "Investment Tool"'
        found_messages = search_emails(service, query)

        if found_messages:
            target_msg = found_messages[0]
            msg_details = service.users().messages().get(userId='me', id=target_msg['id']).execute()
            
            headers = msg_details['payload']['headers']
            subject = next(h['value'] for h in headers if h['name'] == 'Subject')
            
            print(f"Found email: {subject}")
            create_draft(service, 'me', target_msg['threadId'], subject)
        
    except HttpError as error:
        print(f"An error occurred: {error}")

if __name__ == "__main__":
    main()