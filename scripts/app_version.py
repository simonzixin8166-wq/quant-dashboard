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
    "research_planner": "6.13.3",
    "research_execution": "6.13.3",
    "method_memory": "6.14.0",
    "method_evidence_ui": "6.13.4",
    "source_reading_memory": "6.14.0",
    "self_improvement": "7.2.1",
    "learning_evaluation": "6.13.2",
    "system_status": "4",
    "playbook_engine": "6.10a.0",
    "playbook_outcome_foundation": "6.12.1-shadow",
    "forward_learning_feedback": "6.12.1",
    "challenger_experiment_runner": "6.13.0",
    "walk_forward_replay": "6.11.1",
    "controlled_learning_policy": "6.13.2",
    "trigger_ledger_schema": "1.0",
    "replay_history_bootstrap": "1.0.0",
    "market_location_research": "6.10b.1",
    "public_leak_guard": "6.10b.1",
    "range_intelligence": "6.10b.0",
    "private_guardrail": "6.10b.0",
}
