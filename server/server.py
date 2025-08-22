import html
import os
import base64
from email.message import EmailMessage
import requests
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from mcp.server.fastmcp import FastMCP
import uvicorn

# Load environment variables from .env file
load_dotenv()

# Get the absolute path to the directory where this script is located,
# ensuring that file paths are resolved correctly regardless of the
# current working directory.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(SCRIPT_DIR, 'token.json')
CREDENTIALS_PATH = os.path.join(SCRIPT_DIR, 'credentials.json')

mcp = FastMCP('email_generator')

@mcp.prompt(title="Generate Email Prompt")
def generate_email_prompt(context: str) -> str:
    """Generate a prompt for an LLM to generate an email based on the context provided."""
    prompt = f"""
You are an expert email writer. Your task is to generate a professional and clear email.

**Context for the email:**
{context}

Based on the context above, please generate a complete email with the following structure:

**Subject:** [A concise and descriptive subject line]

**Body:**
[A well-written email body that clearly communicates the message based on the provided context. Start with a polite salutation.]

**Closing:**
[A professional closing, such as "Best regards,"]

**Signature:**
[A placeholder for the sender's name, as Sathvik Musku]

Please ensure the tone is professional. Do not add any extra commentary outside of the email structure.
Describe the email in only one paragraph.
"""
    return prompt.strip()

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://mail.google.com/"]

def get_gmail_service():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    "Error: 'credentials.json' not found. "
                    "Please ensure the credentials file is in the same directory as the server script."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    
    return build("gmail", "v1", credentials=creds)


@mcp.tool(title="Send Email")
def send_email(recipient_email: str, subject: str, body: str) -> str:
    """
    Sends an email to a specified recipient with a given subject and body.
    """
    try:
        service = get_gmail_service()
        message = EmailMessage()

        # Convert plain text body to HTML for proper rendering
        escaped_body = html.escape(body)
        html_formatted_body = escaped_body.replace('\n', '<br>')
        html_body = f"<html><body>{html_formatted_body}<br></body></html>"
        message.set_content(html_body, subtype="html")
        message["To"] = recipient_email
        message["From"] = "me"  # 'me' is a special value that uses the authenticated user's email
        message["Subject"] = subject

        # encoded message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {"raw": encoded_message}
        send_message = (
            service.users().messages().send(userId="me", body=create_message).execute()
        )
        print(f'Message Id: {send_message["id"]}')
        return f"Successfully sent email to {recipient_email} with Message ID: {send_message['id']}"
    except HttpError as error:
        print(f"An error occurred: {error}")
        return f"Failed to send email. Error: {error}"
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return f"An unexpected error occurred: {e}"


APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY")

def _enrich_person(params: dict) -> str:
    if not APOLLO_API_KEY:
        raise ValueError("APOLLO_API_KEY environment variable not set.")

    api_endpoint = "https://api.apollo.io/api/v1/people/match"
    
    headers = {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache',
    }
    
    # Add the API key to the parameters
    headers['x-api-key'] = APOLLO_API_KEY
    
    try:
        response = requests.post(api_endpoint, json=params, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()

        if "person" in data and data["person"] and "email" in data["person"] and data["person"]["email"]:
            return f"Email found: {data['person']['email']}"
        else:
            return "Email not found for the given details."

    except requests.exceptions.HTTPError as http_err:
        return f"HTTP error occurred: {http_err} - {response.text}"
    except requests.exceptions.RequestException as req_err:
        return f"Request error occurred: {req_err}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"

@mcp.tool(title="Find Email by Name and Company")
def find_email_by_name_and_company(first_name: str, last_name: str, company_name: str) -> str:
    """
    Finds a person's email by their first name, last name, and company name using Apollo.io.
    """
    params = {
        "first_name": first_name,
        "last_name": last_name,
        "organization_name": company_name,
    }
    return _enrich_person(params)

@mcp.tool(title="Find Email by LinkedIn URL")
def find_email_by_linkedin(linkedin_url: str) -> str:
    """
    Finds a person's email by their LinkedIn URL using Apollo.io.
    """
    params = {
        "person_linkedin_url": linkedin_url,
    }
    return _enrich_person(params)

if __name__ == "__main__":
    mcp.run()
