# Agentic IFRS generation pipeline environment
AZURE_OPENAI_API_KEY=your_key_here
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_GPT52_DEPLOYMENT_URL=https://your-resource.openai.azure.com/openai/deployments/your-strong-deployment/chat/completions?api-version=2024-10-21
AZURE_OPENAI_FAST_DEPLOYMENT_URL=https://your-resource.openai.azure.com/openai/deployments/your-fast-deployment/chat/completions?api-version=2024-10-21

# Optional path overrides
# PAYLOAD_DIR=C:/Users/BV426BP/Documents/IFRS Data/Reporting-Data-/notebooks/gen_data/payloads
# IFRS_REQUIREMENTS_DIR=C:/Users/BV426BP/Documents/IFRS Data/Reporting-Data-/notebooks/gen_data/ifrs_requirements
# STYLE_SYSTEM_DIR=C:/Users/BV426BP/Documents/IFRS Data/Reporting-Data-/notebooks/gen_data/style/style_system
# GENERATION_OUTPUT_DIR=C:/Users/BV426BP/Documents/IFRS Data/Reporting-Data-/notebooks/gen_data/generated_reports/agentic_ifrs_report

PIPELINE_MODE=synthetic_demo
ALLOW_PARTIAL_COVERAGE=true
USE_FUZZY_EVIDENCE_MAPPER=false
MAX_REVISION_LOOPS=2

# To test one section only, uncomment:
# SECTION_TO_RUN=Governance

IFRS_COVERAGE_SCORE_MIN=8.0
EVIDENCE_SCORE_MIN=8.0
STYLE_SCORE_MIN=7.5