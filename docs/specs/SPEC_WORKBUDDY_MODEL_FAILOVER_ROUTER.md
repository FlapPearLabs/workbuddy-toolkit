# Spec: WorkBuddy Model Failover, Auto-Rotation & Model Inventory System

**Status**: Ready for Agent (`ready-for-agent`)  
**Domain**: WorkBuddy Agent Infrastructure / High Availability Runtime & Model Management  
**Author**: Antigravity  
**Version**: 2.0.0  

---

## Problem Statement

When using WorkBuddy for development and background tasks, users face two compounding challenges:

1. **Unattended Execution Stalls & Fragility**:
   - **429 Rate Limit / Quota Exhaustion**: When an active model runs out of free tokens or hits rate limits, WorkBuddy immediately aborts the session, causing long background jobs to halt silently.
   - **Silent First-Token Deadlock**: Upstream network timeouts or queuing deadlocks hold connections open behind default 120s–300s timeouts, leaving conversations hanging indefinitely.
   - **Absence of Client-Side Fallback**: WorkBuddy has no cascading retry mechanism; a single upstream error terminates the turn.

2. **Model Opacity & Lack of Orchestration Controls**:
   - **Scattered Model Sources**: Official WorkBuddy models (stored in application definitions) and third-party custom models (configured in `models.json`) are siloed with no unified inventory.
   - **Credit Multiplier Opacity**: Official models carry wildly varying token cost multipliers (ranging from `0.00x` completely free, `0.06x` ultra-cheap, to `2.00x` expensive), but users cannot view or compare costs from terminal workflows.
   - **Disconnected Usage Habits**: WorkBuddy logs all sessions in local SQLite (`workbuddy.db`), but users have no way to leverage their real historical usage frequency to prioritize models.
   - **Lack of Lightweight Terminal Controls**: There is no interactive terminal selector to inspect available models, view multipliers and usage counts, and adjust fallback priority ranks interactively.

---

## Solution

A cohesive two-tier system consisting of an **Interactive Terminal Control Plane** and a **High-Availability Routing Data Plane**:

1. **Control Plane (`workbuddy models` / `wb-models`)**:
   - **Unified Inventory**: Discovers both official WorkBuddy models (annotated with credit multipliers and capability flags) and third-party custom models (annotated with provider channels).
   - **Usage-Driven Intelligence**: Queries local session history (`workbuddy.db`) to extract exact invocation counts and recency for every model.
   - **Cost & Multiplier Transparency**: Clearly classifies models into cost tiers (`[FREE 0.00x]`, `[0.06x]`, `[0.16x]`, `[0.5x~0.8x]`, `[2.00x]`).
   - **Interactive Terminal Selector (TUI)**: A zero-dependency, lightweight terminal UI for viewing all models, toggling membership in the rotation pool, and dynamically reordering priorities (`Rank 1 -> Rank 2 -> Rank 3...`), with a one-key smart sort (`s`) that balances high usage and low cost.
   - **Deterministic Single Source of Truth**: Saves the selected candidate sequence and thresholds to `~/.workbuddy/failover_router.json`, instantly recognized by the Data Plane.

2. **Data Plane (`FailoverRouter`)**:
   - **Transparent Proxy Gateway**: A local background daemon (`127.0.0.1:8047`) exposing an OpenAI-compatible wire interface (`POST /v1/chat/completions`) registered in WorkBuddy as `workbuddy-autopilot`.
   - **Zero-Leak Pre-Stream Failover**: Intercepts 429, 5xx, and adaptive first-token timeouts (15s for standard models, 45s for deep reasoning models) before any byte is flushed to the client, silently failing over to the next candidate in the user's configured sequence.
   - **Circuit Breaker Cooldown**: Faulted or exhausted models automatically enter a cooldown period (default: 10 minutes), bypassing them in subsequent turns with zero latency penalty.
   - **Host Observability**: Dispatches native macOS notifications upon failover transitions and logs structured execution telemetry without polluting LLM token context.

---

## User Stories

### Control Plane: Model Inventory, Multiplier & Usage
1. As a developer, I want to run `workbuddy models` (or `wb-models`) in my terminal, so that I can see a unified list of all available models across both official WorkBuddy builtins and third-party custom configurations.
2. As a developer, I want to see the credit multiplier for every official model (e.g. `hy3` at `0.00x`, `deepseek-v4-flash` at `0.06x`, `default/Claude` at `2.00x`), so that I know which models are free, cheap, or expensive.
3. As a developer, I want to see how many times I have actually used each model historically (extracted from `workbuddy.db`), so that I can see which models I rely on most.
4. As a developer, I want the system to clearly distinguish official models from third-party models (e.g. Local Proxy, OpenCode Zen), so that I understand where requests are being routed.
5. As a developer, I want each model's capabilities (tool calling, vision, thinking support) clearly displayed, so that I don't select models that cannot support agentic tasks.
6. As a developer, I want an interactive terminal selector where I can move with arrow keys, toggle models in/out of the rotation pool with the Space bar, and adjust priority ranks with `+`/`-` or `J`/`K`, so that I can customize my fallback hierarchy without editing JSON by hand.
7. As a developer, I want a one-key "Smart Rank" command (`s`) in the terminal selector that automatically computes the optimal priority order by placing high-frequency and low-cost/free models at the top, so that I get a sensible configuration with zero effort.
8. As a developer, I want the terminal selector to save my chosen sequence directly to `failover_router.json` upon pressing Enter, so that changes take effect immediately without restarting WorkBuddy.
9. As a scripting user, I want `workbuddy models --json` to output the full model inventory with multipliers and usage stats as structured JSON, so that I can integrate it into automated scripts.

### Data Plane: Resilient Routing & Failover
10. As a developer running background agent sessions, I want WorkBuddy to automatically switch to the next fallback model when the active model returns HTTP 429 or quota exhaustion, so that my background tasks continue progressing.
11. As a developer, I want the failover to execute seamlessly before the first token is flushed to WorkBuddy, so that WorkBuddy's internal tool calling state machine is not corrupted.
12. As a developer using fast models (e.g. Gemini 3.8 Flash, DeepSeek Flash), I want a strict 15-second first-token timeout, so that hung upstream connections are cut off rapidly.
13. As a developer using deep reasoning models (e.g. Claude Opus Thinking, Gemini 3.1 Pro Thinking), I want a relaxed 45-second first-token timeout, so that legitimate long thinking phases are not prematurely aborted.
14. As a developer, I want faulted or exhausted models to enter a 10-minute cooldown state, so that subsequent conversational turns skip known-failed models with zero latency penalty.
15. As a developer, I want models in cooldown to automatically recover when their cooldown expires, so that preferred high-priority models resume service once quota replenishes.
16. As a developer, I want the router to read model URLs, API keys, and reasoning capabilities directly from `models.json`, so that I never duplicate secrets.
17. As a developer, I want a single virtual model entry (`Auto Pilot / 容灾轮换池`) in WorkBuddy's model selector dropdown, so that I can choose between explicit single-model pinning and automatic failover.
18. As a developer working away from the screen, I want a native macOS desktop notification whenever a failover occurs, so that I remain aware of upstream degradation without being interrupted by workflow errors.
19. As a systems builder, I want every failover event, duration, latency metric, and error code recorded in a structured local audit log, so that I have white-box physical evidence to inspect upstream stability.
20. As a user, I want the router daemon to run under macOS `launchd`, so that it starts automatically on system login and recovers from unexpected terminations without manual intervention.
21. As a user, I want the daemon to consume virtually 0.0% CPU when idle and maintain an RSS memory footprint under 10MB, so that running it 24/7 introduces zero performance overhead.
22. As a developer, I want WorkBuddy client updates to never break or overwrite the failover mechanism, so that my failover capability survives application updates without maintenance.
23. As a developer, if all candidate models in the fallback chain are exhausted, I want the router to return a well-formed JSON error response with status 503, so that the client receives a structured, deterministic failure summary instead of an unhandled hang.

---

## Implementation Decisions

### Modules & Seams
1. **Control Plane Module (`workbuddy-toolkit` CLI)**:
   - **`ModelInventory`**: Parser module reading official definitions (`product.json`) and user configurations (`models.json`), merging capability metadata (tool call, vision, reasoning).
   - **`UsageAggregator`**: SQLite reader querying `sessions` in `workbuddy.db` to calculate invocation counts and last-used timestamps.
   - **`TerminalSelector`**: Lightweight ANSI/curses terminal interface presenting the interactive model list, supporting cursor movement, checkbox toggling, priority reordering, smart sorting, and JSON persistence.
   - **CLI Seam**: `workbuddy models` / `wb-models` (terminal UI mode, `--list` flag for text summary, `--json` flag for machine parsing).

2. **Data Plane Module (`FailoverRouter` Daemon)**:
   - Standalone, ultra-lean, event-driven HTTP reverse proxy daemon listening on `127.0.0.1:8047`.
   - **Highest Seam**: Exactly one external seam at the HTTP wire protocol boundary:
     `POST http://127.0.0.1:8047/v1/chat/completions` (OpenAI-compatible wire contract).

### Data Contracts & Single Source of Truth
- **`~/.workbuddy/failover_router.json`**:
  Stores user-selected candidate sequence and thresholds configured via the Control Plane:
  ```json
  {
    "enabled": true,
    "port": 8047,
    "cooldown_seconds": 600,
    "fast_model_timeout_seconds": 15,
    "thinking_model_timeout_seconds": 45,
    "chain": [
      { "id": "hy3", "source": "official" },
      { "id": "deepseek-v4-flash", "source": "official" },
      { "id": "space-bunny-free", "source": "custom" },
      { "id": "gemini-3.8-flash-high", "source": "custom" },
      { "id": "deepseek-v4-pro", "source": "official" }
    ]
  }
  ```
- **`~/.workbuddy/models.json`**:
  Maintains existing custom models and declares the virtual model entry:
  ```json
  {
    "id": "workbuddy-autopilot",
    "name": "Auto Pilot (自动容灾轮换池)",
    "vendor": "FailoverRouter",
    "url": "http://127.0.0.1:8047/v1",
    "apiKey": "sk-workbuddy-router-local",
    "supportsToolCall": true,
    "supportsImages": true,
    "supportsReasoning": true,
    "reasoning": {
      "supportedEfforts": ["high", "medium", "low"],
      "canDisableThinking": true
    }
  }
  ```

### Smart Ranking Algorithm
The smart sort (`s` key in TUI) calculates an affinity score for each model:
$$\text{Score} = w_{\text{usage}} \cdot \log(1 + \text{count}) + w_{\text{cost}} \cdot \frac{1}{1 + \text{multiplier}} + w_{\text{tool}} \cdot \mathbb{I}(\text{supportsToolCall})$$
- Models supporting tool calls receive mandatory qualification.
- Free models (`0.00x`) and ultra-low multiplier models (`0.06x`) with high historical usage naturally bubble to the top.
- High-multiplier models (`2.00x`) or rarely used models are relegated to disaster-recovery tail slots.

### Failover Execution Engine
- When receiving a request for `workbuddy-autopilot`, the router identifies the first non-cooldown candidate in the chain.
- If the candidate is an official model, requests route via WorkBuddy's internal credentials/endpoint; if custom, via the URL/key specified in `models.json`.
- The router peeks at initial response bytes:
  - If HTTP 429, 401, 403, 5xx, or initial timeout elapses before the first token: the candidate enters cooldown, a desktop notification is dispatched, and the request re-dispatches to the next candidate.
  - Once the first valid token chunk arrives, the router switches to transparent streaming pass-through.

---

## Testing Decisions

### What Makes a Good Test
Tests must verify external observable behavior across the agreed seams (CLI command outputs and HTTP wire requests/responses), without testing internal private functions or leaking implementation details.

### Test Scenarios
1. **Model Inventory Discovery**: Verify that `workbuddy models --json` accurately extracts official models from `product.json` (including `credits` multiplier) and custom models from `models.json`.
2. **Usage Aggregation**: Verify that `workbuddy models --json` returns correct historical counts matching actual rows in SQLite `sessions`.
3. **Smart Ranking Calculation**: Verify that models with high frequency and zero/low multiplier rank ahead of zero-usage or high-cost models.
4. **Terminal Selector Key Actions**: Verify that key commands (toggle, reorder, smart rank, save) produce valid JSON output to `failover_router.json`.
5. **Pass-Through Verification**: Upstream returns 200 SSE stream; router forwards chunks verbatim without latency penalty.
6. **429 Failover at HTTP Seam**: Upstream 1 returns HTTP 429; router seamlessly fails over to Upstream 2 and returns a valid 200 SSE stream to the client.
7. **First-Token Timeout Failover**: Upstream 1 hangs for > 15s; router aborts Upstream 1 and completes request via Upstream 2.
8. **Circuit Breaker Cooldown**: Once a model triggers failover, subsequent requests within the cooldown window bypass it immediately.
9. **Chain Exhaustion**: When all upstreams fail, router returns a clean HTTP 503 JSON response.

### Prior Art
- Existing unit and integration tests in `workbuddy-toolkit/tests/test_toolkit.py`.
- Subprocess and HTTP mock server test fixtures in Python standard library.

---

## Out of Scope

1. Direct tampering with WorkBuddy Electron GUI react bundles.
2. In-flight token stitching (attempting to resume a mid-sentence cut from a different model).
3. Cloud synchronization of billing accounts or external quota balances.

---

## Further Notes

- Single source of truth for custom models: `~/.workbuddy/models.json`.
- Single source of truth for failover sequence: `~/.workbuddy/failover_router.json`.
- Daemon binary target: `~/.workbuddy/binaries/failover-router` (or `workbuddy-toolkit/sidecar/failover-router`).
- Daemon LaunchAgent: `~/Library/LaunchAgents/com.workbuddy.failover-router.plist`.
- Audit log destination: `~/.workbuddy/logs/failover_router.log`.
