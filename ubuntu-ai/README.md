# UBUNTU.AI — executive research prototype

Standalone Python CLI for the Ubuntu General Group, attributed to creator Elomar Salvador. This isolated review copy is a local prototype, not connected to or deployed in an existing agent. It uses the Python standard library; Python 3.9+ is recommended. The redirect fix has only been exercised with offline mocks and local loopback servers; no live provider calls have been made for this change, and deployment, availability and production security are not guaranteed.

> **Research and security warning:** This is an experimental prototype, not a fact-checker. The model labels claims as supported; citations can be irrelevant or fail to support them, and no independent verification or semantic entailment check is performed. Untrusted questions, web excerpts, and GitHub metadata may carry prompt-injection instructions that influence the model despite prompt safeguards. Review each claim and its original source before relying on results. Source URLs may contain sensitive query values, and untrusted output may contain terminal control/escape sequences; neither is reliably stripped. Do not use with confidential data or in a sensitive terminal environment.
>
> **Consent scope:** `--allow-external` and the environment-key check apply only to the CLI's `main()`. Calling `research()` directly bypasses both checks and can transmit data externally using the key passed to it; other lower-level API functions can also make network requests. Integrators must implement their own explicit consent and key checks before calling these functions.

## Safety first

- **CLI only:** `main()` blocks external requests unless `--allow-external` is supplied and `ANTHROPIC_API_KEY` is set; this is not enforced by the direct Python API. Do not pass secrets, private client material, or confidential queries. The full question is sent to Anthropic; for technical questions it is also sent to GitHub. Anthropic may submit search queries to its web search service; source excerpts are sent to Anthropic again for synthesis. Costs, provider retention and terms may apply. CLI consent is per invocation, not a guarantee of confidentiality.
- Set secrets in your shell environment or your deployment's secret manager, never in source files, command arguments or Git. Use `ANTHROPIC_API_KEY`; optionally `GITHUB_TOKEN` (for GitHub's search rate limits). Never paste them into chat. `ANTHROPIC_MODEL` is optional and defaults to `claude-sonnet-5-5`; select a model available to your account that supports basic server-side web search. Anthropic web search must be enabled and may incur charges. GitHub search can work without a token but is rate-limited.
- External pages, search snippets, repository metadata, and questions are untrusted. The prompt instructs the model not to follow embedded instructions and the code validates source IDs, but prompt injection remains possible. Do not use for high-stakes decisions without human review.

## Redirect policy and boundaries

`http_json` uses its own urllib opener and **does not follow any HTTP redirects**, even same-origin redirects or requests without credentials. A 3xx response fails as a sanitized `ResearchError` rather than forwarding a header or a POST body. This includes 301, 302, 303, 307 and 308, cross-host, cross-port, scheme changes and HTTPS-to-HTTP downgrades; no first redirect means no redirect chain. If a provider moves an endpoint or redirects for any other reason, the request fails until a trusted endpoint is explicitly updated and reviewed. In the optional GitHub lookup that failure is reported as unverified; Anthropic web-search or synthesis failure prevents a brief.

This does not protect the initial request from an untrusted or compromised destination, a configured proxy, a compromised local environment, or other transmission risks. The built-in API URLs are HTTPS, but direct callers can pass an arbitrary URL, including plain HTTP, and must select trusted HTTPS destinations and enforce consent themselves. urllib can use environment-configured proxies. Avoid placing credentials in URLs. This redirect policy is not a general security guarantee, and tests cannot prove that integrations or the provider behave safely.

## Run

```sh
python -m unittest -v
python demo_offline.py  # fictional mock sources; no network
# Set ANTHROPIC_API_KEY securely in your environment first.
python ubuntu_ai.py --allow-external "What changed in the latest public climate report?"
# Force GitHub discovery for a technical query that the keyword detector misses:
python ubuntu_ai.py --allow-external --technical "Compare approaches to container orchestration"
```

The CLI defaults to blocking transmission; try `python ubuntu_ai.py "A confidential question"` to see the guard. It exits 2 for consent/config errors, 1 for web/synthesis failures, and 0 when a brief is produced. Do not use the prototype's command-line arguments for confidential material: shell history and process lists can expose them.

## How it works

1. It asks Anthropic's Messages API to search the web every time and accepts only a completed response with an actual successful web search result and structured citations. A citation URL must exactly match a URL returned by the web tool; its cited excerpt must be nonempty. A missing search, search error, incomplete response, no matching citations, HTTP error or missing key prevents an answer. There is no fallback to model memory.
2. For automatically detected technical queries, or with `--technical`, it also queries GitHub's public repository search API. Returned `github.com` repository descriptions are discovery hints, not proof of code behavior. If the GitHub request fails or finds no usable repositories, the brief explicitly says so. The simple keyword heuristic misses some technical questions; use `--technical` when in doubt. It does not inspect repository code.
3. A second Anthropic call receives only the collected source excerpts and the question, and is asked for atomic claims as JSON with source IDs, disagreements and uncertainties. Code rejects invalid/unknown source IDs, uncited supported claims, one-source disputes, and claim text containing URLs. The renderer attaches URLs from the provider-result list after URL matching, never from model-generated links. Claims labelled unverified or disputed by the model are displayed accordingly. Claims labelled supported by the model appear under **Model-labelled supported claims**, explicitly noting they are not independently verified and citations may not support them. Results omitted by validation are reported.

**Important limitations:** URL matching only verifies that the provider returned a URL, not that the page exists, is current, authoritative, or supports the claim. The model could still distort excerpts, overlook contradictions, bundle multiple assertions, or misclassify unsupported claims as supported; these checks do not prove semantic entailment or factual truth. Short cited excerpts (Anthropic's web citations can be limited to 150 characters) can omit critical context. GitHub repository descriptions can be inaccurate or malicious. Search may be refused by the model, fail, return no usable citations or hit rate limits; the prototype then fails closed instead of inventing answers. Sources are not opened or independently fact-checked. Technical detection is approximate. Output and source text are not a defense against all prompt injection. A human must review each source and claim before relying on the report.

## Offline tests

`python -m unittest -v` uses mocked provider responses and local loopback HTTP servers, with synthetic test markers; it makes no external network calls. It tests CLI consent/key guards, documents that direct `research()` calls bypass them, checks the model-labelled output heading, required search, citation provenance, invalid claim rejection, disputed claims, GitHub discovery/failure, and an end-to-end mock. Redirect tests exercise every 300–399 status over GET and POST against two local servers, check that the second server is never contacted, cover same-origin and different-host locations, verify normal non-redirect requests, and use a unit-level HTTPS downgrade simulation (not a real HTTPS server). They do **not** establish that citations support claims, prevent prompt injection, establish real provider connectivity, or demonstrate production readiness.

Live use depends on a working network, Anthropic account and valid key, access to a compatible model with web search enabled, and possibly GitHub availability/token/rate limits. The default model name and provider schemas have not been verified by a live request for this change and may not be available or compatible. The intended functionality is not a guarantee of implementation, integration, provider uptime, or correctness.

## API references

- Anthropic web search tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
- GitHub repository search: https://docs.github.com/en/rest/search/search#search-repositories
