"""Demonstrate the pipeline using entirely fictional offline provider responses."""
import json
from unittest.mock import patch
import ubuntu_ai

web = {"stop_reason": "end_turn", "content": [
    {"type": "server_tool_use", "id": "s1", "name": "web_search"},
    {"type": "web_search_tool_result", "tool_use_id": "s1", "content": [
        {"type": "web_search_result", "url": "https://example.com/mock", "title": "Mock source"}]},
    {"type": "text", "text": "A fictional result.", "citations": [
        {"type": "web_search_result_location", "url": "https://example.com/mock", "title": "Mock source", "cited_text": "The fictional sample is blue."}]}]}
synthesis = {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps({"claims": [
    {"text": "The fictional sample is blue.", "status": "supported", "sources": ["W1"]},
    {"text": "The fictional sample's age could not be established.", "status": "unverified", "sources": []}]})}]}
responses = iter([web, synthesis])
print("OFFLINE MOCK DEMO: fictional evidence and example URL; no network requests.\n")
with patch.object(ubuntu_ai, "http_json", side_effect=lambda *args, **kwargs: next(responses)):
    ubuntu_ai.research("What color is the fictional sample?", "dummy-key")
