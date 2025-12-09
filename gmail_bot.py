import os.path
import base64
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
import openai

# Load environment variables (API Keys)
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify"
]

def load_knowledge_base():
    """Reads the policies from the text file."""
    try:
        with open("knowledge_base.txt", "r") as f:
            return f.read()
    except FileNotFoundError:
        print("Error: knowledge_base.txt not found!")
        return ""

def search_emails(service, query):
    """Searches for emails matching the query."""
    try:
        # We exclude emails that already have the 'AI_PROCESSED' label
        query += " -label:AI_PROCESSED"
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        return messages
    except HttpError as error:
        print(f"An error occurred during search: {error}")
        return None

def add_label(service, user_id, msg_id, label_name):
    """Adds a label to an email to mark it as processed."""
    try:
        # 1. Check if label exists, if not create it
        results = service.users().labels().list(userId=user_id).execute()
        labels = results.get('labels', [])
        label_id = next((l['id'] for l in labels if l['name'] == label_name), None)
        
        if not label_id:
            label_object = {'name': label_name}
            created_label = service.users().labels().create(userId=user_id, body=label_object).execute()
            label_id = created_label['id']

        # 2. Apply the label
        body = {'addLabelIds': [label_id]}
        service.users().messages().modify(userId=user_id, id=msg_id, body=body).execute()
        print(f"SUCCESS: Label '{label_name}' added to email.")
    except HttpError as error:
        print(f"An error occurred adding label: {error}")

def create_draft(service, user_id, thread_id, original_subject, email_content):
    """Uses OpenAI to read the knowledge base and draft a reply."""
    try:
        # 1. Read the Knowledge Base
        knowledge_text = load_knowledge_base()
        
        # 2. Ask OpenAI to write the email
        client = openai.OpenAI()
        
        system_prompt = f"""
        You are the AI assistant for BridgesBricks. Use the provided Knowledge Base below to answer the user's email accurately.
        
        GUIDELINES:
        - If they ask about definitions (Scarcity, Part Out, Mismatch), define them exactly as written in the text.
        - If they ask about cost/refunds, clearly state this is a FREE tool for subscribers.
        - Always end with the Disclaimer from the text.
        - Keep the tone enthusiastic, helpful, and professional.
        
        KNOWLEDGE BASE:
        {knowledge_text}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"The user wrote: {email_content}\n\nDraft a reply."}
            ]
        )
        
        draft_body = response.choices[0].message.content

        # 3. Create the Draft Object
        message = EmailMessage()
        message.set_content(draft_body)
        
        if not original_subject.startswith("Re:"):
            message["Subject"] = f"Re: {original_subject}"
        else:
            message["Subject"] = original_subject

        message["To"] = "recipient@example.com"
        message["From"] = user_id
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'message': {'raw': encoded_message, 'threadId': thread_id}}
        
        draft = service.users().drafts().create(userId=user_id, body=create_message).execute()
        print(f"SUCCESS! Draft created. ID: {draft['id']}")
        print("AI Generated Content Preview:\n" + draft_body)
        return draft

    except Exception as error:
        print(f"An error occurred: {error}")
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

        print("Searching for BrickIntel inquiries...")
        # Search for subject line keywords
        query = 'subject:BrickIntel OR "Investment Tool" OR "Factor"' 
        found_messages = search_emails(service, query)

        if found_messages:
            for msg in found_messages:
                msg_details = service.users().messages().get(userId='me', id=msg['id']).execute()
                
                # Get Subject
                headers = msg_details['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
                
                # Get Email Snippet (Body preview)
                snippet = msg_details.get('snippet', '')

                print(f"Found email: {subject}")
                
                # Draft the reply using AI
                create_draft(service, 'me', msg['threadId'], subject, snippet)
                
                # Tag it so we don't reply again
                add_label(service, 'me', msg['id'], 'AI_PROCESSED')
        else:
            print("No new emails found.")
        
    except HttpError as error:
        print(f"An error occurred: {error}")

if __name__ == "__main__":
    main()