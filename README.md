# Market Trends Newsletter Agent

An AI-powered newsletter agent that researches recent U.S. energy-market developments, identifies NRG-relevant trends and opportunities, and generates an HTML market-intelligence newsletter.

The solution uses **Google Vertex AI (Gemini)** for research and report generation, **Tavily** for web search, and **Microsoft Graph API** for email distribution.

## Features

* Researches recent energy-market news and trends
* Focuses on ERCOT, PJM, renewables, regulations, grid developments, and emerging technologies
* Uses Gemini to generate and refine research queries
* Performs web research using Tavily
* Generates an HTML market-trends newsletter
* Supports previous newsletters and earnings-call transcripts as additional context
* Sends the generated newsletter through Microsoft Graph

## Architecture

```text
HTTP Request
     │
     ▼
Newsletter Agent
     │
     ▼
Deep Research
 ┌───────┴────────┐
 ▼                ▼
Tavily         Gemini
Search         Vertex AI
 └───────┬────────┘
         ▼
 Research Findings
         │
         ▼
 Gemini 2.5 Pro
         │
         ▼
 HTML Newsletter
         │
         ▼
 Microsoft Graph
         │
         ▼
 Email Recipients
```

## Tech Stack

* Python
* Google Vertex AI
* Gemini 2.5 Pro / Gemini 2.5 Flash
* Tavily Search API
* Microsoft Graph API
* Azure Identity
* Functions Framework

## Project Structure

```text
├── main.py                 # Application entry point
├── deep_research.py        # Deep research workflow
├── prompts.py              # Research and newsletter prompts
├── graph_client.py         # Microsoft Graph email integration
├── market_trends_report.py # Market report generation
└── requirements.txt
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file:

```env
TAVILY_API_KEY=<your-key>

TENANT_ID=<tenant-id>
CLIENT_ID=<client-id>
CLIENT_SECRET=<client-secret>

ACCOUNT=<sender-mailbox>
RECIPIENTS=user1@example.com,user2@example.com
```

> Do not commit `.env` or credentials to Git.

### 3. Run locally

```bash
functions-framework --target=newsletter --port=8080
```

Trigger the agent:

```bash
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{}'
```

Optional context can also be provided:

```json
{
  "past_newsletter_html": "<html>Previous newsletter...</html>",
  "transcript": "Earnings call transcript..."
}
```

## Workflow

```text
Request
  ↓
Generate Research Queries
  ↓
Search Recent Energy News
  ↓
Analyze & Consolidate Findings
  ↓
Generate Newsletter with Gemini
  ↓
Resolve Source Links
  ↓
Send Email via Microsoft Graph
```

The research primarily covers **energy markets and pricing, renewables, regulatory developments, grid infrastructure, and emerging energy technologies** relevant to NRG.

## Security

Keep all API keys and credentials outside source control. For production deployments, use a managed secret store and apply least-privilege access to Vertex AI and Microsoft Graph.
