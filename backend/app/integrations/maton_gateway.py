"""
Maton AI Gateway API client.

Direct HTTP calls to Maton's gateway API, bypassing problematic
MCP stdio integration. Use this for all Maton tool calls.

Gateway API: https://gateway.maton.ai
Pattern: POST https://gateway.maton.ai/{app-prefix}/{api-path}
Auth: Authorization: Bearer <MATON_API_KEY>

### How it works
- Base URL: https://gateway.maton.ai
- Auth: Bearer <MATON_API_KEY> header
- Pattern: POST https://gateway.maton.ai/{app-prefix}/{native-api-path}
- The {app-prefix} tells Maton which OAuth connection to use
- The rest of the path mirrors the native service API exactly
- Maton automatically injects OAuth token - no connection_id needed for simple calls
- Optional header: Maton-Connection: <connection_id> to pick a specific connection

### Connection management (ctrl.maton.ai)
- List connections: GET https://ctrl.maton.ai/connections
- Filter by app:   GET https://ctrl.maton.ai/connections?app=google-sheets&status=ACTIVE
- Single connection: GET https://ctrl.maton.ai/connections/{connection_id}
- Create connection: POST https://ctrl.maton.ai/connections (user initiates OAuth flow)

### App prefix reference
Each app has a specific prefix that must start the URL path:

| App            | Prefix            | Native API base                         |
|----------------|-------------------|-----------------------------------------|
| Google Sheets  | google-sheet, google-sheets | /google-sheets/v4/spreadsheets/...      |
| Google Sheets  | google-sheets              | /google-sheets/v4/spreadsheets/{id}/...       |
| Google Sheets  | google-sheets              | /google-sheets/v4/spreadsheets/{id}/values/{range}:append |
| Google Sheets  | google-sheets              | /google-sheets/v4/spreadsheets/{id}/values/{range}     |
| Google Sheets  | google-sheets              | /google-sheets/v4/spreadsheets/{id}                  |
| Google Mail    | google-mail, gmail         | /google-mail/gmail/v1/users/me/...      |
| Google Calendar| google-calendar          | /google-calendar/calendar/v3/...        |
| Google Drive   | google-drive              | /google-drive/drive/v3/files/...        |
| Google Docs    | google-docs               | /google-docs/v1/documents/...           |
| Google Slides  | google-slides             | /google-slides/v1/presentations/...   |
| Google Forms   | google-forms              | /google-forms/v1/forms/...                 |
| Google Meet    | google-meet                | /google-meet/v1/conferences/...         |
| Google Ads     | google-ads               | /google-ads/v1/...                   |
| Google Analytics Data | google-analytics-data | /google-analytics-data/v1/...     |
| Google Analytics Admin | google-analytics-admin | /google-analytics-admin/v1/... |
| Google Search Console | google-search-console | /google-search-console/v1/... |
| Google Play     | google-play               | /google-play/androidpublisher/v3/...      |
| YouTube       | youtube                 | /youtube/v3/...                          |
| HubSpot       | hubspot                  | /hubspot/crm/v3/objects/...             |
| Salesforce     | salesforce              | /salesforce/services/data/v59.0/...     |
| Pipedrive     | pipedrive               | /pipedrive/v1/...                       |
| Apollo        | apollo                  | /apollo/graphql                           |
| Asana        | asana                  | /asana/api/1.0/...                      |
| Jira         | jira                   | /jira/rest/api/3/...                    |
| ClickUp       | clickup                | /clickup/v2/...                        |
| Trello        | trello                  | /trello/1/...                          |
| Notion       | notion                  | /notion/v1/...                          |
| Slack         | slack                   | /slack/api/...                          |
| Outlook       | outlook                | /outlook/api/v1.0/me/...                    |
| WhatsApp Business | whatsapp-business        | /whatsapp-business/v1/...                |
| Mailchimp     | mailchimp               | /mailchimp/3.0/...                      |
| Klaviyo       | klaviyo                | /klaviyo/api/...                        |
| Typeform      | typeform                | /typeform/forms/...                     |
| JotForm       | jotform                | /jotform/api/...                        |
| Stripe        | stripe                  | /stripe/v1/...                          |
| QuickBooks    | quickbooks              | /quickbooks/v4/...                     |
| Xero          | xero                   | /xero/api.xro/2.0/...                 |
| WooCommerce  | woocommerce             | /wc/v3/...                            |
| Chargebee     | chargebee               | /chargebee/api/v1/...                   |
| Shopify       | shopify                 | /shopify/admin/api/2024-01/...          |
| Airtable     | airtable                | /airtable/v0/{baseId}/{tableId}         |
| Calendly     | calendly               | /calendly/v1/...                       |
| Fathom       | fathom                  | /fathom/api/v1/...                       |
| LinkedIn      | linkedin                | /linkedin/v2/ugcPosts                   |

### Confirmed working examples
# Create Google Sheet
POST https://gateway.maton.ai/google-sheets/v4/spreadsheets
Body: {"properties": {"title": "My Sheet"}}

# Append rows to sheet
POST https://gateway.maton.ai/google-sheets/v4/spreadsheets/{id}/values/{range}:append
Params: valueInputOption=RAW
Body: {"values": [["col1", "col2"], ["val1", "val2"]]}

# Send Slack message
POST https://gateway.maton.ai/slack/api/chat.postMessage
Body: {"channel": "C0123456", "text": "Hello"}

# Create HubSpot contact
POST https://gateway.maton.ai/hubspot/crm/v3/objects/contacts
Body: {"properties": {"firstname": "John", "lastname": "Doe", "email": "john@example.com"}}

# Create HubSpot company
POST https://gateway.maton.ai/hubspot/crm/v3/objects/companies
Body: {"properties": {"name": "Acme Corp", "website": "acme.com"}}

# Send LinkedIn post
POST https://gateway.maton.ai/linkedin/v2/ugcPosts
Body: LinkedIn UGC post format
"""

import httpx
import logging
from typing import Any, Callable

logger = logging.getLogger("ocin")

GATEWAY_BASE = "https://gateway.maton.ai"
CTRL_BASE = "https://ctrl.maton.ai"

# Complete app name mapping: internal name -> gateway path prefix
APP_GATEWAY_PREFIX = {
    # Google Workspace
    "google-sheet": "google-sheets",
    "google-sheets": "google-sheets",
    "google-mail": "google-mail",
    "gmail": "google-mail",
    "google-calendar": "google-calendar",
    "google-drive": "google-drive",
    "google-docs": "google-docs",
    "google-slides": "google-slides",
    "google-forms": "google-forms",
    "google-meet": "google-meet",
    "google-ads": "google-ads",
    "google-analytics-data": "google-analytics-data",
    "google-analytics-admin": "google-analytics-admin",
    "google-search-console": "google-search-console",
    "google-play": "google-play",
    "youtube": "youtube",
    # CRM / Sales
    "hubspot": "hubspot",
    "salesforce": "salesforce",
    "pipedrive": "pipedrive",
    "apollo": "apollo",
    # Project Management
    "asana": "asana",
    "jira": "jira",
    "clickup": "clickup",
    "trello": "trello",
    "notion": "notion",
    # Communication
    "slack": "slack",
    "outlook": "outlook",
    "whatsapp-business": "whatsapp-business",
    # Marketing
    "mailchimp": "mailchimp",
    "klaviyo": "klaviyo",
    "typeform": "typeform",
    "jotform": "jotform",
    # Finance / Ecommerce
    "stripe": "stripe",
    "quickbooks": "quickbooks",
    "xero": "xero",
    "woocommerce": "woocommerce",
    "chargebee": "chargebee",
    "shopify": "shopify",
    # Data / Productivity
    "airtable": "airtable",
    "calendly": "calendly",
    "fathom": "fathom",
    "linkedin": "linkedin",
}


class MatonGatewayClient:
    """HTTP client for Maton's gateway API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def request(
        self,
        method: str,
        app: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
        connection_id: str | None = None,
    ) -> dict:
        """
        Make a request to Maton gateway API.

        Returns: full JSON response.
        """
        prefix = APP_GATEWAY_PREFIX.get(app, app)
        if not prefix:
            logger.warning({
                "event": "maton_gateway_no_prefix",
                "app": app,
            })
            raise ValueError(f"Unknown Maton app: {app}")

        url = f"{GATEWAY_BASE}/{prefix}/{path.lstrip('/')}"
        headers = dict(self.headers)

        if connection_id:
            headers["Maton-Connection"] = connection_id

        logger.info({
            "event": "maton_gateway_request",
            "method": method,
            "url": url,
        })

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.request(
                method,
                url,
                headers=headers,
                json=body,
                params=params,
            )
            logger.info({
                "event": "maton_gateway_response",
                "status": r.status_code,
                "url": url,
                "preview": r.text[:200] if r.text else "",
            })

            # Improved error handling with clear, actionable messages
            if r.status_code == 500:
                raise ValueError(
                    f"Maton returned 500 for {app}. This usually means that the OAuth "
                    f"token has expired (connections older than ~1 month). "
                    f"Please go to maton.ai, delete the {app} connection, "
                    f"and reconnect it to refresh the OAuth token."
                )
            elif r.status_code == 403:
                raise ValueError(
                    f"Maton returned 403 Forbidden for {app}. "
                    f"The connected account may not have permission for this action, "
                    f"or the connection needs to be reauthorized at maton.ai."
                )
            elif r.status_code == 404:
                raise ValueError(
                    f"Maton returned 404 Not Found for {app}. "
                    f"The requested resource could not be found. Please check your connection settings."
                )
            elif r.status_code >= 400:
                raise ValueError(
                    f"Maton returned {r.status_code} for {app}. "
                    f"Please check your connection at maton.ai and try again."
                )

            r.raise_for_status()
            return r.json() if r.text else {}

    async def create_connection(self, app: str) -> dict:
        """
        Create a new Maton connection for the given app.

        Returns a connection_id and a URL that the user must open
        in their browser to complete OAuth authorization.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{CTRL_BASE}/connections",
                headers=self.headers,
                json={"app": app},
            )
            r.raise_for_status()
            data = r.json()
            conn = data.get("connection", {})
            logger.info({
                "event": "maton_connection_created",
                "app": app,
                "connection_id": conn.get("connection_id"),
            })
            return {
                "connection_id": conn.get("connection_id"),
                "oauth_url": conn.get("url"),
                "status": conn.get("status"),
            }

    async def list_connections(self, app: str | None = None) -> list[dict]:
        """
        List all active Maton connections, optionally filtered by app.

        Returns: list of connection objects with app, connection_id, status.
        """
        params = {"status": "ACTIVE"}
        if app:
            params["app"] = APP_GATEWAY_PREFIX.get(app, app)

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{CTRL_BASE}/connections",
                headers=self.headers,
                params=params,
            )
            r.raise_for_status()
            return r.json().get("connections", [])


def build_google_sheet_tools(api_key: str) -> list:
    """
    Build PydanticAI tool functions for Google Sheets via Maton gateway.

    All tools are async functions that return string results
    for logging and simple agent consumption.

    NOTE: Google Sheets default locale is es_ES (Spanish).
    The default sheet name when creating is "Hoja 1" not "Sheet1".
    If a sheet was created with English locale, use "Sheet1!A1" in ranges.
    """
    client = MatonGatewayClient(api_key)

    async def google_sheet_create_spreadsheet(title: str) -> str:
        """Create a new Google Spreadsheet with a given title."""
        result = await client.request(
            "POST", "google-sheet", "v4/spreadsheets",
            body={"properties": {"title": title}}
        )
        url = result.get("spreadsheetUrl", "")
        sheet_id = result.get("spreadsheetId", "")
        return f"Created spreadsheet '{title}'. ID: {sheet_id}. URL: {url}"

    async def google_sheet_append_rows(
        spreadsheet_id: str,
        values: list,
        range: str = "Hoja 1!A1",
    ) -> str:
        """
        Append rows to a Google Spreadsheet.

        Args:
            spreadsheet_id: The spreadsheet ID
            range: The range to append to. Default is 'Hoja 1!A1' (Spanish locale).
                 Use 'Sheet1!A1' only if the sheet was created in English locale.
            values: List of rows, each row is a list of cell values

        Returns: string summary of appended rows.
        """
        result = await client.request(
            "POST", "google-sheet",
            f"v4/spreadsheets/{spreadsheet_id}/values/{range}:append",
            body={"values": values},
            params={"valueInputOption": "RAW"},
        )
        updates = result.get("updates", {})
        return f"Appended {updates.get('updatedRows', 0)} rows to {range}."

    async def google_sheet_get_values(
        spreadsheet_id: str,
        range: str,
    ) -> str:
        """Get values from a range in a Google Spreadsheet."""
        result = await client.request(
            "GET", "google-sheet",
            f"v4/spreadsheets/{spreadsheet_id}/values/{range}",
        )
        values = result.get("values", [])
        return str(values)

    async def google_sheet_update_values(
        spreadsheet_id: str,
        range: str,
        values: list,
    ) -> str:
        """Update values in a range of a Google Spreadsheet."""
        result = await client.request(
            "PUT", "google-sheet",
            f"v4/spreadsheets/{spreadsheet_id}/values/{range}",
            body={"values": values, "range": range, "majorDimension": "ROWS"},
            params={"valueInputOption": "RAW"},
        )
        return f"Updated {result.get('updatedCells', 0)} cells in {range}."

    async def google_sheet_get_spreadsheet(spreadsheet_id: str) -> str:
        """Get metadata about a Google Spreadsheet including sheet names."""
        result = await client.request(
            "GET", "google-sheet",
            f"v4/spreadsheets/{spreadsheet_id}",
        )
        title = result.get("properties", {}).get("title", "")
        sheets = [s["properties"]["title"] for s in result.get("sheets", [])]
        url = result.get("spreadsheetUrl", "")
        return f"Spreadsheet: '{title}'. Sheets: {sheets}. URL: {url}"

    tools = [
        google_sheet_create_spreadsheet,
        google_sheet_append_rows,
        google_sheet_get_values,
        google_sheet_update_values,
        google_sheet_get_spreadsheet,
    ]

    logger.info({
        "event": "maton_gateway_tools_built",
        "app": "google-sheet",
        "tools": [t.__name__ for t in tools],
    })

    return tools


def build_slack_tools(api_key: str) -> list:
    """
    Build PydanticAI tool functions for Slack via Maton gateway.

    All tools are async functions that return string results.
    """
    client = MatonGatewayClient(api_key)

    async def slack_send_message(channel: str, text: str) -> str:
        """Send a message to a Slack channel. channel is channel ID."""
        result = await client.request(
            "POST", "slack",
            "api/chat.postMessage",
            body={"channel": channel, "text": text},
        )
        return result.get("message", {}).get("ts", "Message sent")

    async def slack_list_channels() -> str:
        """List all Slack channels."""
        result = await client.request(
            "GET", "slack",
            "api/conversations.list",
        )
        channels = result.get("channels", [])
        return ", ".join(c["name"] for c in channels)

    async def slack_get_messages(channel: str, limit: int = 10) -> str:
        """Get recent messages from a Slack channel."""
        result = await client.request(
            "GET", "slack",
            f"api/conversations.history?channel={channel}&limit={limit}",
        )
        messages = result.get("messages", [])
        return ", ".join(m.get("text", "")[:50] for m in messages[:limit])

    tools = [
        slack_send_message,
        slack_list_channels,
        slack_get_messages,
    ]

    logger.info({
        "event": "maton_gateway_tools_built",
        "app": "slack",
        "tools": [t.__name__ for t in tools],
    })

    return tools


def build_hubspot_tools(api_key: str) -> list:
    """
    Build PydanticAI tool functions for HubSpot CRM via Maton gateway.

    All tools are async functions that return string results.
    """
    client = MatonGatewayClient(api_key)

    async def hubspot_create_contact(
        firstname: str,
        lastname: str,
        email: str,
        phone: str = "",
    ) -> str:
        """Create a HubSpot contact."""
        result = await client.request(
            "POST", "hubspot",
            "crm/v3/objects/contacts",
            body={
                "properties": {
                    "firstname": firstname,
                    "lastname": lastname,
                    "email": email,
                    "phone": phone,
                }
            },
        )
        return f"Created contact: {firstname} {lastname}"

    async def hubspot_search_contacts(query: str) -> str:
        """Search HubSpot contacts by name or email."""
        result = await client.request(
            "POST", "hubspot",
            "crm/v3/objects/contacts/search",
            body={
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "email",
                        "operator": "CONTAINS_TOKEN",
                        "value": query
                    }]
                }]
            },
        )
        contacts = result.get("results", [])
        return f"Found {len(contacts)} contacts matching '{query}'"

    async def hubspot_create_company(
        name: str,
        website: str = "",
        phone: str = "",
        address: str = "",
    ) -> str:
        """Create a HubSpot company."""
        result = await client.request(
            "POST", "hubspot",
            "crm/v3/objects/companies",
            body={
                "properties": {
                    "name": name,
                    "website": website,
                    "phone": phone,
                    "address": address,
                }
            },
        )
        return f"Created company: {name}"

    async def hubspot_create_deal(
        dealname: str,
        amount: str = "",
        dealstage: str = "appointmentscheduled",
    ) -> str:
        """Create a HubSpot deal."""
        result = await client.request(
            "POST", "hubspot",
            "crm/v3/objects/deals",
            body={
                "properties": {
                    "dealname": dealname,
                    "amount": amount,
                    "dealstage": dealstage,
                }
            },
        )
        return f"Created deal: {dealname}"

    tools = [
        hubspot_create_contact,
        hubspot_search_contacts,
        hubspot_create_company,
        hubspot_create_deal,
    ]

    logger.info({
        "event": "maton_gateway_tools_built",
        "app": "hubspot",
        "tools": [t.__name__ for t in tools],
    })

    return tools


def build_gmail_tools(api_key: str) -> list:
    """
    Build PydanticAI tool functions for Gmail via Maton gateway.

    All tools are async functions that return string results.
    """
    client = MatonGatewayClient(api_key)

    async def gmail_send_email(
        to: str,
        subject: str,
        body: str = "",
    ) -> str:
        """Send an email via Gmail."""
        result = await client.request(
            "POST", "google-mail",
            "gmail/v1/users/me/messages/send",
            body={"to": to, "subject": subject, "body": body},
        )
        return f"Email sent to {to}"

    async def gmail_list_emails(limit: int = 10) -> str:
        """List recent emails from Gmail."""
        result = await client.request(
            "GET", "google-mail",
            "gmail/v1/users/me/messages",
            params={"maxResults": limit},
        )
        messages = result.get("messages", [])
        return f"Found {len(messages)} recent emails"

    tools = [
        gmail_send_email,
        gmail_list_emails,
    ]

    logger.info({
        "event": "maton_gateway_tools_built",
        "app": "gmail",
        "tools": [t.__name__ for t in tools],
    })

    return tools


def build_generic_tools(api_key: str, app: str) -> list:
    """
    Build a generic tool for any Maton-supported app.

    Used when we don't have specific tool builders yet.
    The agent can call any native API endpoint for that app.
    """
    client = MatonGatewayClient(api_key)
    resolved = APP_GATEWAY_PREFIX.get(app, app)

    async def generic_api_call(
        method: str = "POST",
        body: dict | None = None,
        path: str = "",
    ) -> str:
        """Call any {resolved} API endpoint via Maton gateway.

        The agent can request data to help understand available actions.
        """
        result = await client.request(
            method, app, path, body
        )
        # For generic calls, we return the raw JSON response
        # This allows the agent to see what's available and take appropriate action
        return json.dumps(result)

    async def generic_list_resources() -> str:
        """List available resources/operations for the app."""
        result = await client.request("GET", app, "")
        return json.dumps(result)

    return [
        generic_api_call,
        generic_list_resources,
    ]


def build_maton_gateway_tools(api_key: str, app: str) -> list:
    """
    Factory to build Maton gateway tools for the requested app.

    Returns: list of async tool functions for PydanticAI.

    Supported apps: google-sheet, google-sheets, google-mail, gmail,
                  google-calendar, google-drive, google-docs, slack, hubspot,
                  and 37 other services via generic tools.
    """
    # Map of app to its tool builder function
    builders: dict[str, Callable[[str], list]] = {
        "google-sheet": build_google_sheet_tools,
        "google-sheets": build_google_sheet_tools,
        "slack": build_slack_tools,
        "hubspot": build_hubspot_tools,
        "google-mail": build_gmail_tools,
        "gmail": build_gmail_tools,
    }

    # Use specific builder if available
    builder = builders.get(app)
    if builder:
        logger.info({
            "event": "maton_gateway_using_builder",
            "app": app,
            "builder": builder.__name__,
        })
        return builder(api_key)

    # For any other supported app, return generic tools
    resolved = APP_GATEWAY_PREFIX.get(app, app)
    if resolved in APP_GATEWAY_PREFIX.values():
        logger.info({
            "event": "maton_gateway_using_generic",
            "app": app,
            "resolved_prefix": resolved,
        })
        return build_generic_tools(api_key, app)

    logger.warning({
        "event": "maton_gateway_no_builder",
        "app": app,
        "message": f"No tool builder for {app} yet. Use generic tools.",
    })
    return []
