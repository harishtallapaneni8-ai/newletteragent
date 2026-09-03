import re
import json
import uuid
import math
import datetime
import asyncio
import os

from tavily import TavilyClient
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

load_dotenv()


class ResearchProgress:
    def __init__(self, depth: int, breadth: int):
        self.total_depth = depth
        self.total_breadth = breadth
        self.current_depth = depth
        self.current_breadth = 0
        self.queries_by_depth = {}
        self.query_order = []
        self.query_parents = {}
        self.total_queries = 0
        self.completed_queries = 0
        self.query_ids = {}
        self.root_query = None

    async def start_query(self, query: str, depth: int, parent_query: str = None):
        query_id = str(uuid.uuid4())
        self.query_ids[query] = query_id

        if self.root_query is None:
            self.root_query = query

        if depth not in self.queries_by_depth:
            self.queries_by_depth[depth] = {}

        if query not in self.queries_by_depth[depth]:
            self.queries_by_depth[depth][query] = {
                "completed": False,
                "learnings": [],
                "sources": [],
                "id": self.query_ids[query],
            }

        self.query_order.append(query)

        if parent_query:
            self.query_parents[query] = parent_query

        self.total_queries += 1
        self.current_depth = depth
        self.current_breadth = len(self.queries_by_depth[depth])

        await self._report_progress("query_started")

    async def add_learning(self, query: str, depth: int, learning: str):
        if depth in self.queries_by_depth and query in self.queries_by_depth[depth]:
            self.queries_by_depth[depth][query]["learnings"].append(learning)
            await self._report_progress("learning_added")

    async def complete_query(self, query: str, depth: int):
        if depth in self.queries_by_depth and query in self.queries_by_depth[depth]:
            if not self.queries_by_depth[depth][query]["completed"]:
                self.queries_by_depth[depth][query]["completed"] = True
                self.completed_queries += 1
                await self._report_progress(f"Completed query: {query}")

            parent_query = self.query_parents.get(query)
            if parent_query:
                await self._update_parent_status(parent_query)

    async def add_sources(self, query: str, depth: int, sources: list[dict[str, str]]):
        if depth in self.queries_by_depth and query in self.queries_by_depth[depth]:
            current_sources = self.queries_by_depth[depth][query]["sources"]
            current_urls = {source["url"] for source in current_sources}

            for source in sources:
                if source["url"] not in current_urls:
                    current_sources.append(source)
                    current_urls.add(source["url"])

            await self._report_progress(f"Added sources for query: {query}")

    async def _update_parent_status(self, parent_query: str):
        children = [
            q for q, p in self.query_parents.items()
            if p == parent_query
        ]

        parent_depth = next(
            (
                d for d, queries in self.queries_by_depth.items()
                if parent_query in queries
            ),
            None,
        )

        if parent_depth is not None:
            all_children_complete = all(
                self.queries_by_depth[d][q]["completed"]
                for q in children
                for d in self.queries_by_depth
                if q in self.queries_by_depth[d]
            )

            if all_children_complete:
                await self.complete_query(parent_query, parent_depth)

    async def _report_progress(self, action: str):
        progress_data = {
            "type": "research_progress",
            "action": action,
            "timestamp": datetime.datetime.now().isoformat(),
            "completed_queries": self.completed_queries,
            "total_queries": self.total_queries,
            "progress_percentage": int((self.completed_queries / max(1, self.total_queries)) * 100),
        }

        if self.root_query:
            progress_data["tree"] = self._build_research_tree()

        print(f"[Progress] {action}: {progress_data['progress_percentage']}% complete")

    def _build_research_tree(self):
        def build_node(query):
            depth = next(
                (
                    d for d, queries in self.queries_by_depth.items()
                    if query in queries
                ),
                0,
            )

            data = self.queries_by_depth[depth][query]
            children = [
                q for q, p in self.query_parents.items()
                if p == query
            ]

            return {
                "query": query,
                "id": self.query_ids[query],
                "status": "completed" if data["completed"] else "in_progress",
                "depth": depth,
                "learnings": data["learnings"],
                "sources": data["sources"],
                "sub_queries": [build_node(child) for child in children],
                "parent_query": self.query_parents.get(query),
            }

        if self.root_query:
            return build_node(self.root_query)

        return {}

    def get_learnings_by_query(self):
        learnings = {}

        for depth, queries in self.queries_by_depth.items():
            for query, data in queries.items():
                if data["learnings"]:
                    learnings[query] = data["learnings"]

        return learnings


class DeepSearch:
    def __init__(self, mode: str = "balanced"):
        self.smart_model_id = "gemini-2.5-pro"
        self.fast_model_id = "gemini-2.5-flash"
        self.query_history = set()
        self.mode = mode

        self.client = genai.Client(
            vertexai=True,
            project="prj-nrg-dev-genai",
            location="global",
        )

        self.tavily_client = TavilyClient(
            api_key=os.environ["TAVILY_API_KEY"]
        )

    def determine_research_breadth_and_depth(self, query: str):
        class ResearchParameters(BaseModel):
            breadth: int
            depth: int
            explanation: str

        user_prompt = f"""
Analyze this research query and determine the appropriate breadth and depth.

Query: {query}

Return JSON with:
- breadth: integer between 1-10
- depth: integer between 1-5
- explanation: brief explanation
"""

        generation_config = {
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 2048,
            "response_mime_type": "application/json",
            "response_schema": ResearchParameters,
        }

        try:
            response = self.client.models.generate_content(
                model=self.fast_model_id,
                contents=user_prompt,
                config=generation_config,
            )

            parsed_response = response.parsed

            return {
                "breadth": parsed_response.breadth,
                "depth": parsed_response.depth,
                "explanation": parsed_response.explanation,
            }

        except Exception as e:
            print(f"Error determining research parameters: {str(e)}")

            defaults = {
                "fast": {"breadth": 3, "depth": 1},
                "balanced": {"breadth": 5, "depth": 2},
                "comprehensive": {"breadth": 7, "depth": 3},
            }

            return defaults.get(
                self.mode,
                {"breadth": 5, "depth": 2, "explanation": "Using default values."},
            )

    def generate_follow_up_questions(
        self,
        query: str,
        max_questions: int = 3,
    ):
        class FollowUpQuestions(BaseModel):
            follow_up_queries: list[str]

        user_prompt = f"""
Based on the following user query, generate {max_questions} follow-up questions.

User Query: {query}

Format your response as JSON with key "follow_up_queries".
"""

        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 1024,
            "response_mime_type": "application/json",
            "response_schema": FollowUpQuestions,
        }

        try:
            response = self.client.models.generate_content(
                model=self.smart_model_id,
                contents=user_prompt,
                config=generation_config,
            )

            parsed_response = response.parsed
            return parsed_response.follow_up_queries

        except Exception as e:
            print(f"Error generating follow-up questions: {str(e)}")
            return [f"What are the key aspects of {query}?"]

    async def generate_queries(
        self,
        query: str,
        num_queries: int = 3,
        learnings: list[str] = [],
        previous_queries: set[str] = None,
    ):
        if previous_queries is None:
            previous_queries = set()

        prompt_by_mode = {
            "fast": "Generate concise, focused search queries",
            "balanced": "Generate balanced search queries that explore different aspects",
            "comprehensive": "Generate comprehensive search queries that deeply explore the topic",
        }

        mode_prompt = prompt_by_mode.get(self.mode, prompt_by_mode["balanced"])

        learnings_text = "\n".join([f"- {learning}" for learning in learnings])
        learnings_section = (
            f"\nBased on what we've learned so far:\n{learnings_text}"
            if learnings else ""
        )

        previous_queries_text = "\n".join([f"- {q}" for q in previous_queries])
        previous_queries_section = (
            f"\nPrevious search queries. Avoid repeating these:\n{previous_queries_text}"
            if previous_queries else ""
        )

        user_prompt = f"""
You are a research assistant helping to explore the topic: "{query}"

{mode_prompt}
{learnings_section}
{previous_queries_section}

Generate {num_queries} specific search queries.
Each query should focus on a different aspect or subtopic.
Make the queries specific and well-formed for a search engine.

Format your response as JSON with a "queries" field containing an array of query strings.
"""

        class QueryResponse(BaseModel):
            queries: list[str]

        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8096,
            "response_mime_type": "application/json",
            "response_schema": QueryResponse,
        }

        try:
            response = await self.client.aio.models.generate_content(
                model=self.smart_model_id,
                contents=user_prompt,
                config=generation_config,
            )

            parsed_response = response.parsed
            queries = set(parsed_response.queries)

            unique_queries = set()

            for q in queries:
                is_similar = False

                for prev_q in previous_queries:
                    if await self._are_queries_similar(q, prev_q):
                        is_similar = True
                        break

                if not is_similar:
                    unique_queries.add(q)

            return unique_queries

        except Exception as e:
            print(f"Error generating queries: {str(e)}")
            return {f"{query} - aspect {i + 1}" for i in range(num_queries)}

    def format_text_with_sources(self, answer: str, sources: list[dict]):
        """
        Format text with sources from Tavily response.
        This preserves actual URLs and appends citations.
        """

        if not sources:
            return answer, {}

        sources_dict = {
            i: {
                "link": source.get("url", ""),
                "title": source.get("title", ""),
            }
            for i, source in enumerate(sources)
        }

        formatted_text = answer

        for i, source in sources_dict.items():
            formatted_text += f" [[{i + 1}]]({source['link']})"

        return formatted_text, sources_dict

    async def summarize_with_sources(
        self,
        query: str,
        search_results: list[dict],
        num_follow_up_questions: int = 3,
    ):
        class SummaryResult(BaseModel):
            summary: str
            follow_up_questions: list[str]

        results_text = "\n\n".join(
            [
                f"Source {i + 1}: {res.get('raw_content', '')}"
                for i, res in enumerate(search_results)
            ]
        )

        user_prompt = f"""
Query: {query}

Search Results:
{results_text}

1. Provide a comprehensive answer to the query using the provided search results.
- Include specific dates, figures, numerical data, names, and locations.
- Cite sources using [[1]], [[2]], etc.

2. Generate {num_follow_up_questions} follow-up questions.

Format your response as JSON with:
- summary
- follow_up_questions
"""

        generation_config = {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
            "response_schema": SummaryResult,
        }

        try:
            response = await self.client.aio.models.generate_content(
                model=self.smart_model_id,
                contents=user_prompt,
                config=generation_config,
            )

            parsed_response = response.parsed

            return {
                "summary": parsed_response.summary,
                "follow_up_questions": parsed_response.follow_up_questions,
            }

        except Exception as e:
            print(f"Error summarizing with sources: {str(e)}")

            return {
                "summary": "Could not generate a full summary.",
                "follow_up_questions": [],
            }

    async def search(self, query: str, num_follow_up_questions: int = 3):
        try:
            loop = asyncio.get_event_loop()

            response = await loop.run_in_executor(
                None,
                lambda: self.tavily_client.search(
                    query=query,
                    search_depth="basic",
                    max_results=10,
                    start_date=(datetime.datetime.now() - datetime.timedelta(days=15)).strftime("%Y-%m-%d"),
                    end_date=datetime.datetime.now().strftime("%Y-%m-%d"),
                    country="united states",
                    topic="news",
                    include_raw_content="text",
                    include_answer=False,
                ),
            )

            sources = response.get("results", [])

            if not sources:
                return "", [], {}

            summary_result = await self.summarize_with_sources(
                query,
                sources,
                num_follow_up_questions,
            )

            summary = summary_result.get("summary", "")
            follow_up_questions = summary_result.get("follow_up_questions", [])

            formatted_text, sources_dict = self.format_text_with_sources(summary, sources)

            return formatted_text, follow_up_questions, sources_dict

        except Exception as e:
            print(f"Error during Tavily search: {e}")
            return "", [], {}

    async def process_result(
        self,
        query: str,
        result: str,
        follow_up_questions: list[str],
        num_learnings: int = 3,
    ):
        learnings = [result]

        return {
            "learnings": learnings,
            "follow_up_questions": follow_up_questions,
        }

    async def _are_queries_similar(self, query1: str, query2: str) -> bool:
        if query1.lower() == query2.lower():
            return True

        if len(query1) < 10 or len(query2) < 10:
            return query1.lower() in query2.lower() or query2.lower() in query1.lower()

        class SimilarityResult(BaseModel):
            are_similar: bool

        user_prompt = f"""
Compare these two search queries and determine if they are semantically similar:

Query 1: {query1}
Query 2: {query2}

Return JSON with boolean field "are_similar".
"""

        generation_config = {
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 1024,
            "response_mime_type": "application/json",
            "response_schema": SimilarityResult,
        }

        try:
            response = await self.client.aio.models.generate_content(
                model=self.fast_model_id,
                contents=user_prompt,
                config=generation_config,
            )

            parsed_response = response.parsed
            return parsed_response.are_similar

        except Exception as e:
            print(f"Error comparing queries: {str(e)}")
            return False

    def _merge_results(
        self,
        target_urls: dict[int, dict],
        target_learnings: list[str],
        source_urls: dict[int, dict],
        source_learnings: list[str],
    ):
        if not source_urls:
            target_learnings.extend(source_learnings)
            return

        url_to_target_index = {
            data["link"]: idx
            for idx, data in target_urls.items()
            if data.get("link")
        }

        next_target_index = max(target_urls.keys()) + 1 if target_urls else 0
        source_to_target_map = {}

        for source_idx, source_data in source_urls.items():
            source_url = source_data.get("link")

            if not source_url:
                continue

            if source_url in url_to_target_index:
                source_to_target_map[source_idx] = url_to_target_index[source_url]
            else:
                new_idx = next_target_index
                target_urls[new_idx] = source_data
                url_to_target_index[source_url] = new_idx
                source_to_target_map[source_idx] = new_idx
                next_target_index += 1

        for learning in source_learnings:
            def replace_match(match):
                source_idx = int(match.group(1)) - 1
                new_target_idx = source_to_target_map.get(source_idx)

                if new_target_idx is not None:
                    return f"[[{new_target_idx + 1}]]"

                return match.group(0)

            remapped_learning = re.sub(r'\[\[(\d+)\]\]', replace_match, learning)
            target_learnings.append(remapped_learning)

    async def deep_research(
        self,
        query: str,
        breadth: int,
        depth: int,
        learnings: list[str] = None,
        visited_urls: dict[int, dict] = None,
        parent_query: str = None,
    ):
        if learnings is None:
            learnings = []

        if visited_urls is None:
            visited_urls = {}

        progress = ResearchProgress(depth, breadth)

        await progress.start_query(query, depth, parent_query)

        max_queries = {
            "fast": 5,
            "balanced": 10,
            "comprehensive": 7,
        }[self.mode]

        queries = await self.generate_queries(
            query,
            min(breadth, max_queries),
            learnings,
            previous_queries=self.query_history,
        )

        self.query_history.update(queries)
        unique_queries = list(queries)[:breadth]

        async def process_query(query_str: str, current_depth: int, parent: str = None):
            local_learnings = []
            local_urls = {}

            try:
                await progress.start_query(query_str, current_depth, parent)

                num_follow_up_questions = min(5, math.ceil(breadth / 1.5))

                result = await self.search(query_str, num_follow_up_questions)

                formatted_text, follow_up_questions, new_urls = result
                local_urls = new_urls.copy()

                if new_urls:
                    sources_list = [
                        {
                            "url": url_data["link"],
                            "title": url_data["title"],
                        }
                        for url_data in new_urls.values()
                        if "link" in url_data and "title" in url_data
                    ]

                    await progress.add_sources(query_str, current_depth, sources_list)

                processed_result = await self.process_result(
                    query=query_str,
                    result=formatted_text,
                    follow_up_questions=follow_up_questions,
                    num_learnings=min(5, math.ceil(breadth / 1.5)),
                )

                current_learnings = processed_result["learnings"]

                for learning in current_learnings:
                    await progress.add_learning(query_str, current_depth, learning)

                local_learnings.extend(current_learnings)

                if self.mode == "comprehensive" and current_depth > 1:
                    new_depth = current_depth - 1

                    if processed_result["follow_up_questions"]:
                        follow_up_questions = processed_result["follow_up_questions"][:3]

                        sub_tasks = [
                            process_query(next_query, new_depth, query_str)
                            for next_query in follow_up_questions
                        ]

                        sub_results = await asyncio.gather(*sub_tasks)

                        for sub_res in sub_results:
                            self._merge_results(
                                target_urls=local_urls,
                                target_learnings=local_learnings,
                                source_urls=sub_res["visited_urls"],
                                source_learnings=sub_res["learnings"],
                            )

                await progress.complete_query(query_str, current_depth)

                return {
                    "learnings": local_learnings,
                    "visited_urls": local_urls,
                }

            except Exception as e:
                print(f"Error processing query {query_str}: {str(e)}")
                await progress.complete_query(query_str, current_depth)

                return {
                    "learnings": [],
                    "visited_urls": {},
                }

        tasks = [
            process_query(q, depth, query)
            for q in unique_queries
        ]

        results = await asyncio.gather(*tasks)

        global_learnings = list(learnings)
        global_urls = visited_urls.copy() if visited_urls else {}

        for res in results:
            self._merge_results(
                target_urls=global_urls,
                target_learnings=global_learnings,
                source_urls=res["visited_urls"],
                source_learnings=res["learnings"],
            )

        await progress.complete_query(query, depth)

        research_tree = progress._build_research_tree()

        print(f"Research tree built with {len(global_learnings)} learnings")

        output = {
            "learnings": global_learnings,
            "visited_urls": global_urls,
            "tree": research_tree,
        }

        with open("deep_research_output.json", "w") as f:
            json.dump(output, f)

        return output

    async def close(self):
        try:
            await self.client.aio.aclose()
        except Exception:
            pass
