import os
import re
import json
import asyncio
from datetime import datetime
from urllib.parse import urlparse

from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig
from azure.identity import ClientSecretCredential
from newsletter.graph_client import MSGraphClient

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from newsletter.function_app.deep_research import DeepSearch

load_dotenv()

FAST_LLM = "gemini-2.5-flash"
SMART_LLM = "gemini-2.5-pro"

client = genai.Client(
    vertexai=True,
    project="prj-nrg-dev-genai",
    location="us-central1"
)

# -------------------------------
# STRATEGIC THEMES
# -------------------------------
STRATEGIC_THEMES = """
1. Energy Markets & Pricing (Long-Term Outlook):
- Long-term demand forecasts and load growth projections
- Structural market changes (ERCOT, PJM)
- Commodity price outlook (gas, power, renewables)
- Emerging revenue opportunities (AI/data centers)
- Power generation economics and capacity markets

2. Renewables & Clean Energy:
- Renewable buildout forecasts
- Battery storage trends
- Policy impacts (IRA, incentives)
- Corporate decarbonization
- Grid integration & transmission

3. Regulatory & Policy:
- Federal/state energy policy changes
- FERC/DOE/EPA developments
- Carbon pricing and emissions
- Grid reliability standards

4. Technology & Innovation:
- SMRs, hydrogen, CCUS
- Smart grid & DER growth
- EV infrastructure
- AI/ML in energy
"""

# -------------------------------
# PROMPT TEMPLATE
# -------------------------------
consolidated_article_prompt_template = """
You are an Expert Market Analyst for NRG Energy.

Generate a structured HTML report based on research findings.

CRITICAL RULES:
- Professional tone
- No first-person ("we")
- Focus on last 15 days
- Include citations as superscripts

INPUT:
Strategic Themes: <STRATEGIC_THEMES>
Past Newsletter: <PAST_NEWSLETTER_CONTEXT>
Transcript: <TRANSCRIPT_CONTEXT>
Research Findings: <ANNOTATED_SEARCH_RESULTS>

OUTPUT:
Return full HTML body.
"""

# -------------------------------
# LLM CALL
# -------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(Exception),
)
def generate_consolidated_report(prompt_content: str):
    return client.models.generate_content(
        model=SMART_LLM,
        contents=prompt_content,
        config=GenerateContentConfig(
            temperature=0.0,
            response_modalities=["TEXT"],
            response_mime_type="text/plain",
            thinking_config=ThinkingConfig(
                thinking_budget=4092,
                include_thoughts=False,
            ),
        ),
    )


# -------------------------------
# MAIN REPORT GENERATOR
# -------------------------------
def gen_html_report(
    past_newsletter_html: str = None,
    transcript: str = None
) -> str:

    today = datetime.now().strftime("%B %d, %Y")

    # Initialize DeepSearch
    deep_search = DeepSearch(mode="comprehensive")

    query = f"""
Identify the biggest NRG-relevant news and market shifts
in US energy (ERCOT, PJM, Northeast) from last 15 days.

Focus on:
- regulatory filings
- price shocks
- major announcements
- strategic impacts
"""

    print("Starting Deep Research...")
    results = asyncio.run(
        deep_search.deep_research(query, breadth=4, depth=2)
    )

    learnings = results["learnings"]
    visited_urls = results["visited_urls"]

    annotated_search_results = "\n".join(learnings)

    print("Generating report...")

    # Context handling
    past_context = (
        f"\nPast Newsletter:\n{past_newsletter_html}\n"
        if past_newsletter_html
        else "\nNo past newsletter provided\n"
    )

    transcript_context = (
        f"\nTranscript:\n{transcript}\n"
        if transcript
        else "\nNo transcript provided\n"
    )

    prompt_content = (
        consolidated_article_prompt_template
        .replace("<ANNOTATED_SEARCH_RESULTS>", annotated_search_results)
        .replace("<STRATEGIC_THEMES>", STRATEGIC_THEMES)
        .replace("<PAST_NEWSLETTER_CONTEXT>", past_context)
        .replace("<TRANSCRIPT_CONTEXT>", transcript_context)
    )

    report_response = generate_consolidated_report(prompt_content)

    html_text = report_response.text

    print("Replacing citations with URLs...")

    def replace_link(match):
        link_id = int(match.group(1)) - 1
        source = visited_urls.get(link_id)

        if source:
            url = source.get("link") or source.get("url")
            return f'<a href="{url}">[{link_id+1}]</a>'

        return match.group(0)

    final_html = re.sub(r"\[(\d+)\]", replace_link, html_text)

    return final_html
    print("Replacing link IDs with actual URLs...")
    final_html_report = html_with_placeholders

    def replace_link(match):
        try:
            href_content = match.group(1)
            original_text = match.group(2)
            link_id = None

            if href_content.isdigit():
                link_id = int(href_content)
            elif "Source" in original_text:
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
                            except Exception:
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


if __name__ == "__main__":
    from newsletter.past import PAST_LETTER, TRANSCRIPT

    ATTEMPTS = 1
    max_len = 0
    longest_report = None

    for i in range(ATTEMPTS):
        html_report = gen_html_report(
            past_newsletter_html=PAST_LETTER,
            transcript=TRANSCRIPT
        )

        if len(html_report) > max_len:
            max_len = len(html_report)
            longest_report = html_report

    # TODO: Update recipients list before running in production
    # Replace with actual recipient email addresses
    RECIPIENTS = ["aruna.kuthala@nrg.com"]  # update this for testing

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
        recipients=RECIPIENTS,
        html_body=longest_report,
        send_as="nrggenainewsletter@nrg.com",
    )