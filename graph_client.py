import os
from datetime import datetime, UTC, timedelta
from typing import Optional, List
import logging
import base64
from http import HTTPStatus

from azure.identity import ClientSecretCredential
import requests


class MSGraphClient:
    # CLASS LEVEL CONSTANTS
    SEND_EMAIL_PATTERN = "https://graph.microsoft.com/v1.0/users/{}/sendMail"
    REPLY_TO_EMAIL_PATTERN = "https://graph.microsoft.com/v1.0/users/{}/messages/{}/reply"
    FORWARD_EMAIL_PATTERN = "https://graph.microsoft.com/v1.0/users/{}/messages/{}/forward"
    SCOPES = "https://graph.microsoft.com/.default"

    def __init__(
        self,
        client_secret_credential: ClientSecretCredential,
    ) -> None:
        self._client_secret_credential = client_secret_credential
        self._access_token = None
        self._access_token_expiration = None

    def send_mail(
        self,
        account: str,
        subject: Optional[str],
        recipients: List[str],
        html_body: str,
        send_as: Optional[str] = None,
        cc_recipients: Optional[List[str]] = None,
        bcc_recipients: Optional[List[str]] = None,
        attachment_file_paths: Optional[List[str]] = None,
    ):
        file_attachments = []

        try:
            if attachment_file_paths:
                for file_path in attachment_file_paths:
                    with open(file_path, "rb") as f:
                        file_content = f.read()
                    file_name = os.path.basename(file_path)
                    file_content_encoded = base64.b64encode(file_content).decode("utf-8")

                    file_attachments.append({
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": file_name,
                        "contentBytes": file_content_encoded
                    })

            new_message = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML",
                        "content": html_body
                    },
                    "toRecipients": [
                        {"emailAddress": {"address": recipient}}
                        for recipient in recipients
                    ],
                    "from": {
                        "emailAddress": {
                            "address": send_as if send_as else account
                        }
                    },
                    "ccRecipients": [
                        {"emailAddress": {"address": cc_recipient}}
                        for cc_recipient in cc_recipients
                    ] if cc_recipients else [],
                    "bccRecipients": [
                        {"emailAddress": {"address": bcc_recipient}}
                        for bcc_recipient in bcc_recipients
                    ] if bcc_recipients else [],
                    "attachments": file_attachments
                }
            }

            headers = {
                "Authorization": "Bearer " + self._get_token(),
                "Content-Type": "application/json"
            }

            resp = requests.post(
                url=self.SEND_EMAIL_PATTERN.format(account),
                headers=headers,
                json=new_message
            )

            if resp.status_code == HTTPStatus.ACCEPTED:
                logging.info("Successfully sent new email")
            else:
                logging.error(
                    f"Failed to send new email. Status code: {resp.status_code}, Response: {resp.text}"
                )
                raise Exception(
                    f"Failed to send new email. Status code: {resp.status_code}, Response: {resp.text}"
                )

        except Exception as ex:
            logging.error(f"Error sending new email: {str(ex)}")
            logging.error("Full exception traceback:\n", exc_info=True)
            raise

    def reply_to_mail(
        self,
        account: str,
        original_message_id: str,
        subject: Optional[str],
        recipients: List[str],
        html_body: str,
        cc_recipients: Optional[List[str]] = None,
        bcc_recipients: Optional[List[str]] = None,
        attachment_file_paths: Optional[List[str]] = None,
    ):
        file_attachments = []

        try:
            if attachment_file_paths:
                for file_path in attachment_file_paths:
                    with open(file_path, "rb") as f:
                        file_content = f.read()
                    file_name = os.path.basename(file_path)
                    file_content_encoded = base64.b64encode(file_content).decode("utf-8")

                    file_attachments.append({
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": file_name,
                        "contentBytes": file_content_encoded
                    })

            reply_message = {
                "comment": html_body,
                "message": {
                    "subject": subject,
                    "toRecipients": [
                        {"emailAddress": {"address": recipient}}
                        for recipient in recipients
                    ],
                    "ccRecipients": [
                        {"emailAddress": {"address": cc_recipient}}
                        for cc_recipient in cc_recipients
                    ] if cc_recipients else [],
                    "bccRecipients": [
                        {"emailAddress": {"address": bcc_recipient}}
                        for bcc_recipient in bcc_recipients
                    ] if bcc_recipients else [],
                    "attachments": file_attachments
                }
            }

            headers = {
                "Authorization": "Bearer " + self._get_token(),
                "Content-Type": "application/json"
            }

            resp = requests.post(
                url=self.REPLY_TO_EMAIL_PATTERN.format(account, original_message_id),
                headers=headers,
                json=reply_message
            )

            if resp.status_code == HTTPStatus.ACCEPTED:
                logging.info(f"Successfully replied to email with message ID: {original_message_id}")
            else:
                logging.error(
                    f"Failed to reply to email with message ID: {original_message_id}. "
                    f"Status code: {resp.status_code}, Response: {resp.text}"
                )
                raise Exception(
                    f"Failed to reply to email. Status code: {resp.status_code}, Response: {resp.text}"
                )

        except Exception as ex:
            logging.error(f"Error replying to email: {str(ex)}")
            logging.error("Full exception traceback:\n", exc_info=True)
            raise

    def forward_mail(
        self,
        account: str,
        original_message_id: str,
        subject: Optional[str],
        recipients: List[str],
        html_body: str,
        cc_recipients: Optional[List[str]] = None,
        bcc_recipients: Optional[List[str]] = None,
        attachment_file_paths: Optional[List[str]] = None,
    ):
        file_attachments = []

        try:
            if attachment_file_paths:
                for file_path in attachment_file_paths:
                    with open(file_path, "rb") as f:
                        file_content = f.read()
                    file_name = os.path.basename(file_path)
                    file_content_encoded = base64.b64encode(file_content).decode("utf-8")

                    file_attachments.append({
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": file_name,
                        "contentBytes": file_content_encoded
                    })

            forward_message = {
                "comment": html_body,
                "message": {
                    "subject": subject,
                    "toRecipients": [
                        {"emailAddress": {"address": recipient}}
                        for recipient in recipients
                    ],
                    "ccRecipients": [
                        {"emailAddress": {"address": cc_recipient}}
                        for cc_recipient in cc_recipients
                    ] if cc_recipients else [],
                    "bccRecipients": [
                        {"emailAddress": {"address": bcc_recipient}}
                        for bcc_recipient in bcc_recipients
                    ] if bcc_recipients else [],
                    "attachments": file_attachments
                }
            }

            headers = {
                "Authorization": "Bearer " + self._get_token(),
                "Content-Type": "application/json"
            }

            resp = requests.post(
                url=self.FORWARD_EMAIL_PATTERN.format(account, original_message_id),
                headers=headers,
                json=forward_message
            )

            if resp.status_code == HTTPStatus.ACCEPTED:
                logging.info(f"Successfully forwarded email with message ID: {original_message_id}")
            else:
                logging.error(
                    f"Failed to forward email with message ID: {original_message_id}. "
                    f"Status code: {resp.status_code}, Response: {resp.text}"
                )
                raise Exception(
                    f"Failed to forward email. Status code: {resp.status_code}, Response: {resp.text}"
                )

        except Exception as ex:
            logging.error(f"Error forwarding email: {str(ex)}")
            logging.error("Full exception traceback:\n", exc_info=True)
            raise

    def _get_token(self) -> str:
        # Get new token if not exists
        if not self._access_token:
            access_token = self._client_secret_credential.get_token(self.SCOPES)
            self._access_token = access_token.token
            self._access_token_expiration = datetime.fromtimestamp(
                access_token.expires_on, tz=UTC
            )

        # Refresh token if near expiry (5 min buffer)
        if self._access_token_expiration <= (datetime.now(UTC) + timedelta(minutes=5)):
            access_token = self._client_secret_credential.get_token(self.SCOPES)
            self._access_token = access_token.token
            self._access_token_expiration = datetime.fromtimestamp(
                access_token.expires_on, tz=UTC
            )

        return self._access_token