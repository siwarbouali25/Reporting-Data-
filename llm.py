# 5. Azure OpenAI client setup

import os
from openai import AzureOpenAI

# Required Azure variables:
# AZURE_OPENAI_API_KEY
# AZURE_OPENAI_ENDPOINT
# AZURE_OPENAI_API_VERSION
# AZURE_OPENAI_DEPLOYMENT

required_vars = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
]

missing = [v for v in required_vars if not os.getenv(v)]

if missing:
    print("Missing environment variables:")
    for v in missing:
        print("-", v)

    print("\nSet them before running API cells.")
else:
    print("Azure OpenAI environment variables found.")

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)

# In Azure, MODEL must be your DEPLOYMENT NAME, not just the base model name.
MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT")

print("Azure client ready.")
print("Endpoint:", os.getenv("AZURE_OPENAI_ENDPOINT"))
print("Deployment:", MODEL)
print("API version:", os.getenv("AZURE_OPENAI_API_VERSION"))