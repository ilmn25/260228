"""Gmail utilities backed by Google Gmail API."""

from __future__ import annotations

import os
import base64
from typing import Any
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

try:
	from dotenv import load_dotenv
	load_dotenv()
except Exception:
	pass


class GmailError(RuntimeError):
	"""Raised when Gmail API operations fail."""


def _get_gmail_service(email: str = ""):
    """Get an authenticated Gmail API service.

    Requires the following **environment variables** be defined:

    - `GOOGLE_TOKEN_FILE`: path to an OAuth token JSON file created by the
      `add_oauth_token` flow.
    - `GOOGLE_APPLICATION_CREDENTIALS`: path to a service account JSON key file.
    - `GOOGLE_DEFAULT_EMAIL` (optional): default email to use when email parameter is empty.

    One of the variables **must** be set; otherwise a `GmailError` is raised.
    
    Args:
        email: Email account to use. If empty, uses GOOGLE_DEFAULT_EMAIL from environment.
    """
    token_path_str = os.environ.get("GOOGLE_TOKEN_FILE")
    creds_path_str = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not token_path_str and not creds_path_str:
        raise GmailError(
            "Environment variables GOOGLE_TOKEN_FILE or "
            "GOOGLE_APPLICATION_CREDENTIALS must be set"
        )

    creds = None

    if token_path_str:
        import json
        token_path = Path(token_path_str)
        if not token_path.exists():
            raise GmailError(f"Token file not found: {token_path}")
        
        # Load token file (multi-email format)
        with open(token_path, "r", encoding="utf-8") as f:
            token_data = json.load(f)
        
        target_email = email or os.environ.get("GOOGLE_DEFAULT_EMAIL", "")
        
        if not target_email:
            # If no email specified and no default, use the first available
            if token_data:
                target_email = list(token_data.keys())[0]
            else:
                raise GmailError("No tokens found in token.json")
        
        if target_email not in token_data:
            available = ", ".join(token_data.keys())
            raise GmailError(
                f"No token found for email '{target_email}'. "
                f"Available emails: {available}"
            )
        
        creds = OAuthCredentials.from_authorized_user_info(token_data[target_email])
    elif creds_path_str:
        creds_path = Path(creds_path_str)
        if not creds_path.exists():
            raise GmailError(f"Credentials file not found: {creds_path}")
        creds = service_account.Credentials.from_service_account_file(
            str(creds_path),
            scopes=[
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/gmail.send',
                'https://www.googleapis.com/auth/gmail.modify'
            ]
        )
    
    if creds and creds.expired and hasattr(creds, 'refresh_token'):
        creds.refresh(Request())

    return build('gmail', 'v1', credentials=creds)


async def list_emails(
	ctx: Context[ServerSession, None],
	query: str = "",
	max_results: int = 8,
	email: str = "",
) -> dict[str, Any]:
	"""Get Gmail emails matching a query.
	
	Args:
		query: Gmail search query (e.g., "from:user@example.com", "is:unread").
		max_results: Maximum number of emails to return (default: 8).
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with list of matching emails and email details.
	"""
	try:
		service = _get_gmail_service(email)
		results = service.users().messages().list(
			userId='me',
			q=query,
			maxResults=max_results
		).execute()
		
		emails = results.get('messages', [])
		email_list = []
		
		for msg in emails:
			msg_data = service.users().messages().get(
				userId='me',
				id=msg['id'],
				format='full'
			).execute()
			
			headers = msg_data['payload'].get('headers', [])
			subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
			sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
			date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
			
			email_list.append({
				'id': msg['id'],
				'subject': subject,
				'from': sender,
				'date': date,
				'snippet': msg_data.get('snippet', ''),
			})
		
		await ctx.info(f"Found {len(email_list)} emails matching query: {query}")
		return {'emails': email_list, 'count': len(email_list)}
	except HttpError as error:
		raise GmailError(f"Failed to get emails: {error}") from error


async def send_email(
	ctx: Context[ServerSession, None],
	to: str,
	subject: str,
	body: str,
	cc: str = "",
	bcc: str = "",
	email: str = "",
) -> dict[str, str]:
	"""Send an email via Gmail.
	
	Args:
		to: Recipient email address.
		subject: Email subject.
		body: Email body (plain text or HTML).
		cc: CC recipients (comma-separated).
		bcc: BCC recipients (comma-separated).
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with the sent email ID.
	"""
	try:
		service = _get_gmail_service(email)
		
		message = {
			'raw': base64.urlsafe_b64encode(
				f"""From: me
To: {to}
Subject: {subject}
{f'Cc: {cc}' if cc else ''}
{f'Bcc: {bcc}' if bcc else ''}

{body}""".encode()
			).decode()
		}
		
		sent_message = service.users().messages().send(
			userId='me',
			body=message
		).execute()
		
		await ctx.info(f"Email sent to {to} with subject '{subject}'")
		return {'email_id': sent_message['id'], 'status': 'sent'}
	except HttpError as error:
		raise GmailError(f"Failed to send email: {error}") from error


async def get_labels(
	ctx: Context[ServerSession, None],
	email: str = "",
) -> dict[str, list]:
	"""Get all Gmail labels.
	
	Args:
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with list of all labels.
	"""
	try:
		service = _get_gmail_service(email)
		results = service.users().labels().list(userId='me').execute()
		
		labels = results.get('labels', [])
		label_list = [
			{'id': label['id'], 'name': label['name']}
			for label in labels
		]
		
		await ctx.info(f"Retrieved {len(label_list)} labels")
		return {'labels': label_list, 'count': len(label_list)}
	except HttpError as error:
		raise GmailError(f"Failed to get labels: {error}") from error


async def mark_as_read(
	ctx: Context[ServerSession, None],
	email_id: str,
	email: str = "",
) -> dict[str, str]:
	"""Mark a Gmail email as read.
	
	Args:
		email_id: The Gmail email ID.
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with status.
	"""
	try:
		service = _get_gmail_service(email)
		service.users().messages().modify(
			userId='me',
			id=email_id,
			body={'removeLabelIds': ['UNREAD']}
		).execute()
		
		await ctx.info(f"Marked email {email_id} as read")
		return {'email_id': email_id, 'status': 'marked as read'}
	except HttpError as error:
		raise GmailError(f"Failed to mark email as read: {error}") from error


async def mark_as_unread(
	ctx: Context[ServerSession, None],
	email_id: str,
	email: str = "",
) -> dict[str, str]:
	"""Mark a Gmail email as unread.
	
	Args:
		email_id: The Gmail email ID.
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with status.
	"""
	try:
		service = _get_gmail_service(email)
		service.users().messages().modify(
			userId='me',
			id=email_id,
			body={'addLabelIds': ['UNREAD']}
		).execute()
		
		await ctx.info(f"Marked email {email_id} as unread")
		return {'email_id': email_id, 'status': 'marked as unread'}
	except HttpError as error:
		raise GmailError(f"Failed to mark email as unread: {error}") from error

async def delete_email(
	ctx: Context[ServerSession, None],
	email_id: str,
	email: str = "",
) -> dict[str, str]:
	"""Delete a Gmail email.
	
	Args:
		email_id: The Gmail email ID.
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with status.
	"""
	try:
		service = _get_gmail_service(email)
		service.users().messages().delete(
			userId='me',
			id=email_id
		).execute()
		
		await ctx.info(f"Deleted email {email_id}")
		return {'email_id': email_id, 'status': 'deleted'}
	except HttpError as error:
		raise GmailError(f"Failed to delete email: {error}") from error

async def get_email_details(
	ctx: Context[ServerSession, None],
	email_id: str,
	email: str = "",
) -> dict[str, Any]:
	"""Get full details of a Gmail email.
	
	Args:
		email_id: The Gmail email ID.
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with complete email details.
	"""
	try:
		service = _get_gmail_service(email)
		msg_data = service.users().messages().get(
			userId='me',
			id=email_id,
			format='full'
		).execute()
		
		headers = msg_data['payload'].get('headers', [])
		subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
		sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
		date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
		to = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
		
		body = ""
		if 'parts' in msg_data['payload']:
			for part in msg_data['payload']['parts']:
				if part['mimeType'] == 'text/plain':
					data = part['body'].get('data', '')
					if data:
						body = base64.urlsafe_b64decode(data).decode('utf-8')
					break
		else:
			data = msg_data['payload']['body'].get('data', '')
			if data:
				body = base64.urlsafe_b64decode(data).decode('utf-8')
		
		await ctx.info(f"Retrieved details for email {email_id}")
		return {
			'id': email_id,
			'subject': subject,
			'from': sender,
			'to': to,
			'date': date,
			'body': body[:500],  # Return first 500 chars
			'snippet': msg_data.get('snippet', ''),
		}
	except HttpError as error:
		raise GmailError(f"Failed to get message details: {error}") from error


async def get_drafts(
	ctx: Context[ServerSession, None],
	max_results: int = 8,
	email: str = "",
) -> dict[str, Any]:
	"""Get all Gmail drafts.
	
	Args:
		max_results: Maximum number of drafts to return (default: 8).
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with list of draft messages.
	"""
	try:
		service = _get_gmail_service(email)
		results = service.users().messages().list(
			userId='me',
			q='in:draft',
			maxResults=max_results
		).execute()
		
		messages = results.get('messages', [])
		draft_list = []
		
		for msg in messages:
			msg_data = service.users().messages().get(
				userId='me',
				id=msg['id'],
				format='full'
			).execute()
			
			headers = msg_data['payload'].get('headers', [])
			subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
			to = next((h['value'] for h in headers if h['name'] == 'To'), '')
			
			draft_list.append({
				'id': msg['id'],
				'subject': subject,
				'to': to,
				'snippet': msg_data.get('snippet', ''),
			})
		
		await ctx.info(f"Retrieved {len(draft_list)} drafts")
		return {'drafts': draft_list, 'count': len(draft_list)}
	except HttpError as error:
		raise GmailError(f"Failed to get drafts: {error}") from error


async def create_draft(
	ctx: Context[ServerSession, None],
	to: str,
	subject: str,
	body: str,
	cc: str = "",
	bcc: str = "",
	email: str = "",
) -> dict[str, str]:
	"""Create a Gmail draft.
	
	Args:
		to: Recipient email address.
		subject: Draft subject.
		body: Draft body (plain text or HTML).
		cc: CC recipients (comma-separated).
		bcc: BCC recipients (comma-separated).
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with the draft message ID.
	"""
	try:
		service = _get_gmail_service(email)
		
		message = {
			'raw': base64.urlsafe_b64encode(
				f"""From: me
To: {to}
Subject: {subject}
{f'Cc: {cc}' if cc else ''}
{f'Bcc: {bcc}' if bcc else ''}

{body}""".encode()
			).decode()
		}
		
		draft = service.users().drafts().create(
			userId='me',
			body={'message': message}
		).execute()
		
		await ctx.info(f"Created draft with subject '{subject}'")
		return {'draft_id': draft['id'], 'status': 'created'}
	except HttpError as error:
		raise GmailError(f"Failed to create draft: {error}") from error


async def update_draft(
	ctx: Context[ServerSession, None],
	draft_id: str,
	to: str = "",
	subject: str = "",
	body: str = "",
	cc: str = "",
	bcc: str = "",
	email: str = "",
) -> dict[str, str]:
	"""Update a Gmail draft.
	
	Args:
		draft_id: The draft ID to update.
		to: New recipient email address.
		subject: New draft subject.
		body: New draft body.
		cc: New CC recipients (comma-separated).
		bcc: New BCC recipients (comma-separated).
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with status.
	"""
	try:
		service = _get_gmail_service(email)
		
		# Get the current draft to preserve fields not specified
		draft_data = service.users().drafts().get(
			userId='me',
			id=draft_id
		).execute()
		
		msg_data = draft_data['message']
		headers = msg_data.get('payload', {}).get('headers', [])
		
		# Use provided values or keep existing ones
		final_to = to or next((h['value'] for h in headers if h['name'] == 'To'), '')
		final_subject = subject or next((h['value'] for h in headers if h['name'] == 'Subject'), '')
		final_body = body or ''
		final_cc = cc or next((h['value'] for h in headers if h['name'] == 'Cc'), '')
		final_bcc = bcc or next((h['value'] for h in headers if h['name'] == 'Bcc'), '')
		
		message = {
			'raw': base64.urlsafe_b64encode(
				f"""From: me
To: {final_to}
Subject: {final_subject}
{f'Cc: {final_cc}' if final_cc else ''}
{f'Bcc: {final_bcc}' if final_bcc else ''}

{final_body}""".encode()
			).decode()
		}
		
		service.users().drafts().update(
			userId='me',
			id=draft_id,
			body={'message': message}
		).execute()
		
		await ctx.info(f"Updated draft {draft_id}")
		return {'draft_id': draft_id, 'status': 'updated'}
	except HttpError as error:
		raise GmailError(f"Failed to update draft: {error}") from error


async def delete_draft(
	ctx: Context[ServerSession, None],
	draft_id: str,
	email: str = "",
) -> dict[str, str]:
	"""Delete a Gmail draft.
	
	Args:
		draft_id: The draft ID to delete.
		email: Email account to use (empty for default).
	
	Returns:
		Dictionary with status.
	"""
	try:
		service = _get_gmail_service(email)
		service.users().drafts().delete(
			userId='me',
			id=draft_id
		).execute()
		
		await ctx.info(f"Deleted draft {draft_id}")
		return {'draft_id': draft_id, 'status': 'deleted'}
	except HttpError as error:
		raise GmailError(f"Failed to delete draft: {error}") from error
