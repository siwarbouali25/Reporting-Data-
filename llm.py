import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(override=True)

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
key = os.getenv("AZURE_OPENAI_API_KEY")

print("Endpoint:", endpoint)
print("Deployment:", deployment)
print("API version:", api_version)
print("Key loaded:", key is not None)
print("Key length:", len(key) if key else None)
print("Key prefix:", key[:4] if key else None)

client = AzureOpenAI(
    api_key=key,
    api_version=api_version,
    azure_endpoint=endpoint,
)

response = client.chat.completions.create(
    model=deployment,
    messages=[{"role": "user", "content": "Reply with: Azure works"}],
    max_tokens=20,
)

print(response.choices[0].message.content)