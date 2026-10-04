"""Single source of truth for MyAlpha View release and asset versions.

Version policy:
- APP_VERSION changes only for user-visible product releases.
- Internal engines keep independent component versions.
- A component version must never be presented as the website/app version.
"""

APP_VERSION = "6.9.0"
ASSET_VERSION = APP_VERSION
OPTIONS_VERSION = "4.1.0"

COMPONENT_VERSIONS = {
    "learning_engine": "5.4.0",
    "autonomous_agent": "5.5.0",
    "research_planner": "6.8.2",
    "research_execution": "6.9.0",
    "method_memory": "5.9.2",
    "self_improvement": "7.2.1",
    "learning_evaluation": "6.9.0",
    "system_status": "4",
    "playbook_engine": "6.10a.0",
    "trigger_ledger_schema": "1.0",
    "market_location_research": "6.10b.1",
    "public_leak_guard": "6.10b.1",
    "range_intelligence": "6.10b.0",
    "private_guardrail": "6.10b.0",
}
