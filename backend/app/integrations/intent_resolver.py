import logging
import json
from typing import Optional

from pydantic import BaseModel
from app.core.system_model import run_system_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent as AgentModel

logger = logging.getLogger("ocin")

# Valid canonical values per provider — used only for LLM prompt as reference,
# NOT for matching logic (the LLM does the matching)
MATON_VALID_APPS = [
    "airtable", "asana", "aws", "calendly", "clickup", "google-calendar",
    "google-docs", "google-drive", "google-mail", "google-sheet", "hubspot",
    "jira", "jotform", "klaviyo", "mailchimp", "notion", "outlook",
    "pipedrive", "salesforce", "shopify", "slack", "stripe", "typeform", "youtube"
]

COMPOSIO_VALID_TOOLKITS = [
    "gmail", "googlecalendar", "googledrive", "googlesheets", "googledocs",
    "slack", "notion", "github", "jira", "linear", "asana", "hubspot",
    "salesforce", "pipedrive", "airtable", "dropbox", "onedrive", "zoom",
    "twitter", "linkedin", "instagram", "facebook", "youtube",
    "stripe", "shopify", "mailchimp", "sendgrid", "typeform",
    "trello", "monday", "clickup", "basecamp", "figma", "miro",
    "zendesk", "intercom", "freshdesk", "discord", "telegram",
]

APIFY_VALID_TOOLS = [
    "actors", "docs", "apify/rag-web-browser", "apify/web-scraper",
    "apify/cheerio-scraper", "apify/playwright-scraper",
    "apify/google-search-scraper", "apify/instagram-scraper",
    "apify/twitter-scraper", "apify/linkedin-scraper",
]

PROVIDER_VALID_VALUES = {
    "maton": MATON_VALID_APPS,
    "composio": COMPOSIO_VALID_TOOLKITS,
    "apify": APIFY_VALID_TOOLS,
}


class IntentResolution(BaseModel):
    """Structured output from intent resolution LLM."""
    provider: Optional[str]  # "maton" | "composio" | "apify" | None
    app: Optional[str]  # canonical app/toolkit name
    confidence: str  # "high" | "low"
    display_name: str  # human-friendly name
    confirmation_message: str  # what agent should say to user
    clarification_message: str  # what to say if confidence is low


async def resolve_integration_intent(
    db: AsyncSession,
    user_id: str,
    user_input: str,
) -> IntentResolution:
    """Use user's coordinator model to interpret what integration the user wants.

    Returns an IntentResolution with a canonical provider and app name,
    plus pre-written confirmation and clarification messages for the agent to use.

    Falls back to a low-confidence result if user has no coordinator or call fails.
    """
    valid_apps_context = json.dumps(PROVIDER_VALID_VALUES, indent=2)

    system_prompt = """You are an integration name resolver. Given a user's description

## GLOBAL REFERENCE
of an integration they want to connect, identify:
1. The provider: one of "maton", "composio", or "apify"
2. The exact canonical app/toolkit name from the valid values list
3. Your confidence: "high" if you are sure, "low" if ambiguous

Respond ONLY with a JSON object, no markdown, no explanation:
{
  "provider": "maton" | "composio" | "apify" | null,
  "app": "<exact canonical name from valid list>" | null,
  "confidence": "high" | "low",
  "display_name": "<human friendly name in user's language>",
  "confirmation_message": "<friendly confirmation in user's language>",
  "clarification_message": "<friendly question in user's language if unsure>"
}

If the provider is unclear, set provider to null and confidence to "low".
If the app name is unclear but the provider is known, set app to null and confidence to "low".
"""

    user_message = f"""Valid integration values:
{valid_apps_context}

User said: "{user_input}"

Resolve this to a canonical provider and app name."""

    result = await run_system_task(
        db=db,
        user_id=user_id,
        system_prompt=system_prompt,
        user_message=user_message,
        result_type=IntentResolution,
        max_tokens=400,
        temperature=0.0,
    )

    if result is None:
        return IntentResolution(
            provider=None,
            app=None,
            confidence="low",
            display_name=user_input,
            confirmation_message="",
            clarification_message=(
                f"I wasn't sure which integration you meant by \"{user_input}\". "
                f"Could you clarify?"
            ),
        )
    return result