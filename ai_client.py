# ai_client.py
from openai import OpenAI
import os

def get_azure_openai_client() -> OpenAI:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION")

    base_url = endpoint.rstrip("/") + "/openai"

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_query={"api-version": api_version},
        default_headers={"api-key": api_key},
    )

def get_deployment_name() -> str:
    return os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
