import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

import ubuntu_ai as u


def web_response():
    return {"stop_reason": "end_turn", "content": [
        {"type": "server_tool_use", "id": "tool_1", "name": "web_search", "input": {"query": "example"}},
        {"type": "web_search_tool_result", "tool_use_id": "tool_1", "content": [
            {"type": "web_search_result", "url": "https://example.com/fact", "title": "Example"}]},
        {"type": "text", "text": "Claim.", "citations": [
            {"type": "web_search_result_location", "url": "https://example.com/fact",
             "title": "Example", "cited_text": "The sample result is blue."}]}]}


def message(payload):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(payload)}]}


class Tests(unittest.TestCase):
    def test_no_consent_no_key_no_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(u, "http_json") as network, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(u.main(["What happened?"]), 2)
            self.assertEqual(u.main(["What happened?", "--allow-external"]), 2)
            network.assert_not_called()

    def test_direct_research_bypasses_cli_consent_and_environment_key_checks(self):
        evidence = [{"id": "W1", "url": "https://example.com", "title": "Example", "excerpt": "Example", "kind": "web"}]
        with patch.dict(os.environ, {}, clear=True), patch.object(u, "search_web", return_value=evidence) as search, patch.object(u, "synthesize", return_value=([], 0)), contextlib.redirect_stdout(io.StringIO()):
            u.research("Question", "passed-key")
        search.assert_called_once_with("Question", "passed-key", u.MODEL)

    def test_supported_heading_warns_that_model_labels_are_not_verified(self):
        evidence = [{"id": "W1", "url": "https://example.com", "title": "Example", "excerpt": "The sky is blue.", "kind": "web"}]
        # Structural source-ID validation cannot prove the excerpt supports the claim.
        response = message({"claims": [{"text": "The sky is green.", "status": "supported", "sources": ["W1"]}]})
        claims, rejected = u.synthesize("q", evidence, "k", "m", lambda payload, key: response)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            u.render(claims, evidence, rejected)
        self.assertIn("Model-labelled supported claims (not independently verified; citations may not support the claims):", out.getvalue())
        self.assertIn("The sky is green.", out.getvalue())
        self.assertEqual(rejected, 0)

    def test_web_requires_actual_successful_search_and_citation(self):
        evidence = u.search_web("example", "dummy", "model", lambda payload, key: web_response())
        self.assertEqual(evidence[0]["url"], "https://example.com/fact")
        for response in [message({"claims": []}), {"stop_reason": "max_tokens", "content": []},
                         {"stop_reason": "end_turn", "content": [
                             {"type": "server_tool_use", "id": "a", "name": "web_search"},
                             {"type": "web_search_tool_result", "tool_use_id": "a", "content": {"type": "web_search_tool_result_error", "error_code": "unavailable"}}]}]:
            with self.assertRaises(u.ResearchError):
                u.search_web("example", "dummy", "model", lambda payload, key: response)

    def test_invented_and_unsafe_citation_rejected(self):
        response = web_response()
        response["content"][2]["citations"][0]["url"] = "https://invented.example/"
        with self.assertRaises(u.ResearchError):
            u.search_web("example", "dummy", "model", lambda payload, key: response)
        self.assertFalse(u.safe_url("javascript:alert(1)"))
        self.assertFalse(u.safe_url("https://user:password@example.com"))

    def test_synthesis_rejects_invalid_claims_and_dispute_needs_two(self):
        evidence = u.search_web("q", "k", "m", lambda payload, key: web_response())
        response = message({"claims": [
            {"text": "The sample is blue.", "status": "supported", "sources": ["W1"]},
            {"text": "Invented", "status": "supported", "sources": ["W999"]},
            {"text": "No support", "status": "supported", "sources": []},
            {"text": "Different reports", "status": "disputed", "sources": ["W1"]},
            {"text": "Go to https://evil.example", "status": "supported", "sources": ["W1"]},
            {"text": "The exact value is unverified.", "status": "unverified", "sources": []}]})
        claims, rejected = u.synthesize("q", evidence, "k", "m", lambda payload, key: response)
        self.assertEqual(len(claims), 2)
        self.assertEqual(rejected, 4)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            u.render(claims, evidence, rejected)
        self.assertIn("https://example.com/fact", out.getvalue())
        self.assertIn("UNVERIFIED", out.getvalue())
        self.assertNotIn("invented.example", out.getvalue())

    def test_disagreement_rendered_with_both_sources(self):
        evidence = [{"id": "W1", "url": "https://a.example", "excerpt": "A", "title": "A"},
                    {"id": "W2", "url": "https://b.example", "excerpt": "B", "title": "B"}]
        response = message({"claims": [{"text": "Sources disagree about the value.", "status": "disputed", "sources": ["W1", "W2"]}]})
        claims, rejected = u.synthesize("q", evidence, "k", "m", lambda payload, key: response)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            u.render(claims, evidence, rejected)
        self.assertIn("DISPUTED", out.getvalue())
        self.assertIn("https://a.example", out.getvalue())
        self.assertIn("https://b.example", out.getvalue())

    def test_github_filters_host_and_sends_token_in_header(self):
        captured = {}
        def fake(url, headers):
            captured.update(url=url, headers=headers)
            return {"items": [{"html_url": "https://github.com/org/repo", "full_name": "org/repo", "description": "Demo"},
                              {"html_url": "https://github.com.evil.test/repo", "description": "wrong"}]}
        found = u.search_github("python code", "dummy-token", fake)
        self.assertEqual(len(found), 1)
        self.assertIn("python%20code", captured["url"])
        self.assertNotIn("dummy-token", captured["url"])
        self.assertEqual(captured["headers"]["Authorization"], "Bearer dummy-token")

    def test_github_failure_is_exposed_not_silently_ignored(self):
        evidence = [{"id": "W1", "url": "https://a.example", "title": "A", "excerpt": "A", "kind": "web"}]
        with patch.object(u, "search_web", return_value=evidence), patch.object(u, "search_github", side_effect=u.ResearchError("failed")), patch.object(u, "synthesize", return_value=([], 0)), contextlib.redirect_stdout(io.StringIO()) as out:
            u.research("python", "dummy", technical=True)
        self.assertIn("GitHub repository search failed", out.getvalue())
        self.assertIn("UNVERIFIED", out.getvalue())

    def test_bad_synthesis_json_fails_closed(self):
        with self.assertRaises(u.ResearchError):
            u.synthesize("q", [], "k", "m", lambda payload, key: {"stop_reason": "end_turn", "content": [{"type": "text", "text": "not json"}]})

    def test_full_mocked_research(self):
        outputs = [web_response(), message({"claims": [{"text": "The sample result is blue.", "status": "supported", "sources": ["W1"]}]})]
        def fake(payload, key):
            return outputs.pop(0)
        with patch.object(u, "anthropic", side_effect=fake), contextlib.redirect_stdout(io.StringIO()) as out:
            # Default callable args are bound at definition time, so inject at the network boundary.
            with patch.object(u, "http_json", side_effect=lambda url, payload=None, headers=None: outputs.pop(0)):
                u.research("sample", "dummy")
        self.assertIn("Model-labelled supported claims", out.getvalue())
        self.assertIn("https://example.com/fact", out.getvalue())
        self.assertEqual(outputs, [])


if __name__ == "__main__":
    unittest.main()
