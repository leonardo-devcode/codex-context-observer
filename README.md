# Codex Context Observer

A local context dashboard and per-conversation cost estimator for Codex desktop.

An independent plugin, not affiliated with OpenAI. English interface. Version **0.4.1**.

## Install from GitHub

Requirements: Codex desktop with plugin/MCP Apps support, Codex CLI with `plugin marketplace`, and **Python 3.10+** available as `python3` on the application PATH. Installation has been tested on macOS with Codex CLI 0.163.0. Automated tests also run on Linux; full desktop integration on other operating systems has not been validated.

```sh
codex plugin marketplace add leonardo-devcode/codex-context-observer
codex plugin add context-observer@codex-context-observer
```

You can also select **Context Observer** from the marketplace list in the interface and install **Conversation context**. Restart Codex, then ask in the conversation you want to monitor:

> Open the context panel for this conversation.

On first launch, the plugin creates an isolated Python environment and installs `tiktoken` and its dependencies using pip. This step requires internet access and may take a few minutes. Subsequent launches reuse the environment. The tokenizer vocabulary and compiled HTML are included; Node.js is not required to use the plugin.

Each panel stays bound to the conversation in which it was opened. Data updates every two seconds while the panel is visible. To monitor another conversation, open a panel there.

### Update

```sh
codex plugin marketplace upgrade codex-context-observer
codex plugin add context-observer@codex-context-observer
```

Restart Codex and reopen the panel. Check the version in the header. To uninstall, use plugin management in Codex. The Python cache is not removed automatically.

If you installed the earlier local edition (`context-observer@leonardo-context-local`), disable it in the interface before enabling this edition to avoid duplicate tools. Installing from GitHub does not modify or remove the earlier edition.

## What the panel shows

- Estimated context window usage, input/output from the last call, and history.
- A partial breakdown of recorded text, in tokens and as a percentage of the window.
- An inventory of skills and MCP namespaces present in the session, with details and search.
- Compaction history with measurements before and after each compaction.
- USD estimates by model when there is evidence of OpenAI API billing.
- Plugin version, conversation identity, and update status.

The plugin makes no calls to the model or billing API. It does not automatically follow the conversation selected in the interface.

## Billing detection

The plugin prioritizes authentication recorded for the response/turn or evidence of a ChatGPT plan associated with the turn. When billing information is missing from the history, it may use `codex login status` as a local reference, checked at most once per minute. Raw command output and credentials are never returned to the panel.

**The current API login does not prove historical billing or which account the desktop app used.** In that case, the panel labels the source of the estimate. Usage identified as ChatGPT is excluded from API estimates. Conflicting evidence remains unpriced. If responses are explicitly identified as API usage, the subtotal includes only those responses.

Usage comes from per-response token records (`token_usage_record`), deduplicated by ID. The model comes from the response or its turn. Recorded service tiers take priority; **Standard is the assumed reference** when the tier is missing. Cache and reasoning tokens are not counted twice. Long-context pricing is applied per call.

The rates in `pricing.json` were checked on **October 17, 2026** and do not update automatically. They are applied to the history without reconstructing historical rates. Models and providers without listed rates remain unpriced. The estimate is not an invoice: it excludes taxes, discounts, separately billed tools, regional surcharges, and subagents stored in other files.

## Privacy and limitations

Collection reads the SQLite index and the conversation JSONL file inside `CODEX_HOME` (by default, `~/.codex`). This internal format may change. Conversations without compatible local records are not supported.

Processing is local. The interface receives metrics, the conversation name/ID, source paths, and resource inventories, which may contain private names and references. It does not receive raw message/instruction text or keys. There is no telemetry or transmission to a project server. Avoid publishing screenshots or reports containing private information. Initial setup accesses the Python package registry to download dependencies.

Context composition uses `o200k_base` as an approximation; it has not been confirmed as the exact tokenizer for the model. Categories may overlap and **must not be added together**. Encrypted and multimodal content is excluded. After compaction, estimates use readable preserved history and new records. Tools without an accessible catalog remain unavailable.

Panel labels and messages are in English. Conversation names and catalog content are displayed as recorded in the session. Numbers use English formatting, and timestamps use the device time zone.

## Troubleshooting

- **MCP fails to start:** verify that `python3 --version` works in the Codex environment. On Linux, you may need your distribution's `python3-venv` package. Check startup logs and connectivity to the Python registry on first launch.
- **Categories unavailable:** check that the tokenizer was installed and the session contains the corresponding records. The plugin does not invent fallback values.
- **Cost unavailable:** the session may use ChatGPT, lack detailed counters, or have no matching rates. For an API account, verify CLI authentication with `codex login status`.
- **Conversation not found:** the panel supports only active local sessions in the `state_5.sqlite` index. Archived files, remote sessions, and format changes may prevent collection.
- **Binding expired:** close the panel and open a new one in the same conversation.

The Python environment is stored in `~/Library/Caches/codex-context-observer` on macOS or `${XDG_CACHE_HOME:-~/.cache}/codex-context-observer` on other systems. Set `CONTEXT_OBSERVER_DATA_DIR` to choose a different cache directory. The global Python environment is not modified.

## Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r plugins/context-observer/requirements.txt
npm ci --prefix plugins/context-observer
npm run build --prefix plugins/context-observer
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
node tests/test_billing_ui.mjs
node tests/test_fixed_bridge.mjs
node tests/test_ui_state.mjs
```

The compiled `panel.html` is committed so users can install without Node. Rebuild it after changing the interface. Tests use synthetic data and do not require API keys or real conversations.

## License and references

Original code is licensed under MIT; third-party notices are in [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt).

- [Codex plugins and marketplaces](https://developers.openai.com/plugins/build/plugins)
- [Codex authentication](https://developers.openai.com/codex/auth)
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- [Per-call cost calculation](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api)
