import logging
from google.cloud import secretmanager
from viur.core.config import conf

"""
This module provides utility functions for accessing values stored in the Google Cloud Secret Manager.
"""

# Global secret manager client instance
__client = secretmanager.SecretManagerServiceClient()


def get(secret: str, version: int | str = "latest") -> str:
    """
    Retrieves a secret stored in Google Cloud Secret Manager for use within the application.

    Add a secret online under https://console.cloud.google.com/security/secret-manager.
    Service accounts requires the role "Secret Manager Secret Accessor" in IAM.
    """
    name = f"""projects/{conf.instance.project_id}/secrets/{secret}/versions/{version}"""
    return __client.access_secret_version(request={"name": name}).payload.data.decode()
