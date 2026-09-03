import os
import re
import asyncio
from datetime import datetime
from urllib.parse import urlparse
from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig
from azure.identity import ClientSecretCredential
from graph_client import MSGraphClient
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from deep_research import DeepSearch
from prompts import STRATEGIC_THEMES, CONSOLIDATED_ARTICLE_PROMPT_TEMPLATE
import functions_framework

load_dotenv()

FAST_LLM = "gemini-2.5-flash"
SMART_LLM = "gemini-2.5-pro"

client = genai.Client(
    vertexai=True,
    project="prj-nrg-dev-genai",
    location="us-central1"
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((Exception,))
)
def generate_consolidated_report(prompt_content: str):
    """Generate consolidated HTML report with retry logic."""
    return client.models.generate_content(
        model=SMART_LLM,
        contents=prompt_content,
        config=GenerateContentConfig(
            temperature=0.0,
            response_modalities=["TEXT"],
            response_mime_type="text/plain",
            thinking_config=ThinkingConfig(
                thinking_budget=4092,
                include_thoughts=False
            )
        ),
    )


def gen_html_report(past_newsletter_html: str = None, transcript: str = None) -> str:
    today = datetime.now().strftime("%B %d, %Y")

    # Initialize DeepSearch
    deep_search = DeepSearch(mode="comprehensive")

    # Construct query
    query = f"""
    Identify the biggest NRG-relevant news and market shifts in the US energy sector
    (specifically ERCOT, PJM, Northeast) from the last 15 days.

    Focus on new announcements, recent market shifts, regulatory filings,
    and price shocks related to these themes:

    {STRATEGIC_THEMES}

    The goal is to answer:
    "What's the biggest NRG-relevant news in the last 2 weeks,
    and what does it mean for us?"

    Prioritize factual, recent events over general trends.
    """

    # Run deep research
    print("Starting Deep Research...")
    results = asyncio.run(deep_search.deep_research(query, breadth=4, depth=2))

    learnings = results["learnings"]
    visited_urls = results["visited_urls"]

    annotated_search_results = "\n".join(learnings)

    print("Generating consolidated article and HTML report...")

    # Past newsletter context
    if past_newsletter_html:
        past_newsletter_context = f"\n\nPast Newsletter Content:\n---\n{past_newsletter_html}\n---\n"
    else:
        past_newsletter_context = "\n\nNo past newsletter provided.\n"

    # Transcript context
    if transcript:
        transcript_context = f"\n\nNRG Earnings Call Transcript:\n---\n{transcript}\n---\n"
    else:
        transcript_context = "\n\nNo transcript provided.\n"

    prompt_content = (
        CONSOLIDATED_ARTICLE_PROMPT_TEMPLATE
        .replace("<ANNOTATED_SEARCH_RESULTS>", annotated_search_results)
        .replace("<TODAY>", today)
        .replace("<STRATEGIC_THEMES>", STRATEGIC_THEMES)
        .replace("<PAST_NEWSLETTER_CONTEXT>", past_newsletter_context)
        .replace("<TRANSCRIPT_CONTEXT>", transcript_context)
    )

    report_response = generate_consolidated_report(prompt_content)

    html_with_placeholders = ""
    try:
        html_start = report_response.text.index("```html") + 7
        html_end = report_response.text.index("```", html_start)
        html_with_placeholders = report_response.text[html_start:html_end]
    except ValueError:
        html_with_placeholders = report_response.text

    print("Replacing link IDs with actual URLs...")
    final_html_report = html_with_placeholders

    def replace_link(match):
        try:
            href_content = match.group(1)
            original_text = match.group(2)
            link_id = None

            if href_content.isdigit():
                link_id = int(href_content)
            else:
                id_match = re.search(r"Source\s*(\d+)", original_text)
                if id_match:
                    link_id = int(id_match.group(1))
                elif re.match(r"^\[\d+\]$", original_text):
                    link_id = int(original_text.strip("[]"))

            if link_id is not None:
                idx = link_id - 1
                source_data = visited_urls.get(idx) or visited_urls.get(str(idx))

                if source_data:
                    url = source_data.get("link") or source_data.get("url")

                    if url:
                        if re.match(r"^\[\d+\]$", original_text):
                            return f'<a href="{url}">{original_text}</a>'

                        domain = source_data.get("title")
                        if not domain:
                            try:
                                domain = urlparse(url).netloc
                            except:
                                domain = original_text

                        return f'<a href="{url}">{domain}</a>'

            return match.group(0)

        except (ValueError, IndexError):
            return match.group(0)

    final_html_report = re.sub(
        r'<a href="([^"]+)">([^<]*)</a>',
        replace_link,
        final_html_report
    )

    return final_html_report


@functions_framework.http
def newsletter(request):
    """HTTP Cloud Function entry point."""

    request_json = request.get_json(silent=True)

    past_newsletter_html = None
    transcript = None

    if request_json:
        past_newsletter_html = request_json.get("past_newsletter_html")
        transcript = request_json.get("transcript")

    # Generate report
    html_report = gen_html_report(
        past_newsletter_html=past_newsletter_html,
        transcript=transcript,
    )

    # Send via email
    recipients = [
        e.strip()
        for e in os.environ.get("RECIPIENTS", "").split(",")
        if e.strip()
    ]

    graph_client = MSGraphClient(
        client_secret_credential=ClientSecretCredential(
            tenant_id=os.environ.get("TENANT_ID"),
            client_id=os.environ.get("CLIENT_ID"),
            client_secret=os.environ.get("CLIENT_SECRET"),
        )
    )

    graph_client.send_mail(
        account=os.environ.get("ACCOUNT"),
        subject=f"{datetime.now().strftime('%b %d, %Y')} - NRG Market Trends and Opportunities",
        recipients=recipients,
        html_body=html_report,
        send_as="nrggeneanewsletter@nrg.com",
    )

    return "ok"