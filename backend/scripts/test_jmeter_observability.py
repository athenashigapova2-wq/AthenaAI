"""Offline structural checks for the JMeter-to-Grafana test contour."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
JMX_PATH = BACKEND_ROOT / "load_tests" / "jmeter" / "athena-agent-smoke.jmx"
RUNNER_PATH = (
    BACKEND_ROOT / "load_tests" / "jmeter" / "run-smoke-with-grafana.ps1"
)
CAPACITY_RUNNER_PATH = (
    BACKEND_ROOT / "load_tests" / "jmeter" / "run-capacity-with-grafana.ps1"
)
DASHBOARD_PATH = (
    REPO_ROOT
    / "observability"
    / "grafana"
    / "dashboards"
    / "jmeter-load-tests.json"
)


def check_jmeter_plan() -> None:
    root = ElementTree.parse(JMX_PATH).getroot()

    error_action = root.find(".//stringProp[@name='ThreadGroup.on_sample_error']")
    assert error_action is not None
    assert error_action.text == "startnextloop"

    expected_properties = {
        "ThreadGroup.num_threads": "${__P(users,5)}",
        "ThreadGroup.ramp_time": "${__P(rampSeconds,30)}",
        "LoopController.loops": "${__P(loops,5)}",
    }
    actual_properties = {
        name: root.find(f".//*[@name='{name}']").text
        for name in expected_properties
    }
    assert actual_properties == expected_properties

    listeners = root.findall(".//BackendListener")
    assert len(listeners) == 1
    assert listeners[0].attrib.get("enabled") == "true"
    class_name = listeners[0].find("./stringProp[@name='classname']")
    assert class_name is not None
    assert class_name.text is not None
    assert class_name.text.endswith("InfluxdbBackendListenerClient")

    listener_arguments = {
        argument.find("./stringProp[@name='Argument.name']").text:
        argument.find("./stringProp[@name='Argument.value']").text
        for argument in listeners[0].findall(".//elementProp[@elementType='Argument']")
    }
    assert listener_arguments["application"] == "${__P(application,athena-agent)}"
    assert listener_arguments["percentiles"] == "50;95;99"
    assert listener_arguments["summaryOnly"] == "false"

    runner = RUNNER_PATH.read_text(encoding="utf-8")
    for expected_default in (
        "[int]$Users = 5",
        "[int]$RampSeconds = 30",
        "[int]$Loops = 5",
        '[string]$Scenario = "baseline-5x5"',
    ):
        assert expected_default in runner
    assert "$missingE2E" in runner
    assert "$plannedErrorRate" in runner
    assert "00000000-0000-0000-0000-000000000000" in runner
    assert "Token preflight passed" in runner
    assert "$tokenProbeStatus -eq 401" in runner
    assert "$tokenSource = $tokenSource -replace '[\\p{C}\\p{Z}]', ''" in runner
    assert "$jwtMatches = [regex]::Matches(" in runner
    assert "(?<jwt>eyJ[A-Za-z0-9_-]*" in runner
    assert "$jwtMatches.Count -ne 1" in runner
    assert "$accessToken = $jwtMatches[0].Groups['jwt'].Value" in runner
    assert "$env:LOAD_TEST_ACCESS_TOKEN = $accessToken" in runner
    assert "exactly one valid three-segment JWT" in runner
    assert "Get-JwtExpirationUtc" in runner
    assert "$requiredTokenLifetimeSeconds" in runner
    assert "expires too soon for this stage" in runner
    assert '$runId = "$Scenario-$timestamp"' in runner
    assert '$application = "athena-agent-$runId"' in runner
    assert '"-Japplication=$application"' in runner
    assert "var-application=$encodedApplication" in runner
    assert "$summaryFile" in runner
    assert "Get-NearestRankPercentile" in runner
    assert "$grafanaFromMs = [long][math]::Max(" in runner
    assert "[double]($testStartMs - 5000)" in runner
    assert "[ValidateRange(1, 1000)]" in runner
    assert "$enqueueResults" in runner
    assert "enqueue_p95_ms" in runner
    assert "$maxActiveUsers" in runner
    assert "max_active_users = $maxActiveUsers" in runner

    capacity_runner = CAPACITY_RUNNER_PATH.read_text(encoding="utf-8")
    assert "AGENT_INFRASTRUCTURE_TEST_MODE" in capacity_runner
    assert "LLM_PROVIDER" in capacity_runner
    assert "10, 20, 40, 80, 120" in capacity_runner
    assert "planned_error_rate_percent" in capacity_runner
    assert "max_active_users" in capacity_runner
    assert "capacity-results" in capacity_runner


def check_grafana_dashboard() -> None:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    variables = dashboard["templating"]["list"]
    assert len(variables) == 1
    assert variables[0]["name"] == "application"
    assert variables[0]["label"] == "Load-test run"
    assert variables[0]["includeAll"] is False
    assert variables[0]["regex"] == "/^athena-agent-/"

    panel_queries = [
        target["query"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "query" in target
    ]
    assert panel_queries
    assert all('r.application == "${application}"' in query for query in panel_queries)
    assert all('r.application == "athena-agent"' not in query for query in panel_queries)

    failed_panel = next(
        panel
        for panel in dashboard["panels"]
        if panel["title"] == "Failed E2E scenarios"
    )
    query = failed_panel["targets"][0]["query"]

    assert 'r.transaction == "agent_chat_e2e"' in query
    assert 'r.statut == "ko"' in query
    assert failed_panel["fieldConfig"]["defaults"]["noValue"] == "0"

    latency_panel = next(panel for panel in dashboard["panels"] if panel["id"] == 1)
    assert "interval latency" in latency_panel["title"]

    active_users_panel = next(
        panel for panel in dashboard["panels"] if panel["title"] == "Active users (max)"
    )
    active_users_query = active_users_panel["targets"][0]["query"]
    assert "|> max()" in active_users_query
    assert "|> last()" not in active_users_query

    throughput_panel = next(
        panel
        for panel in dashboard["panels"]
        if panel["title"] == "E2E throughput (scenarios/s, 5 s interval)"
    )
    throughput_query = throughput_panel["targets"][0]["query"]
    assert 'r.transaction == "agent_chat_e2e"' in throughput_query
    assert 'r.statut == "all"' in throughput_query
    assert 'r.transaction != "internal"' not in throughput_query


def main() -> None:
    check_jmeter_plan()
    check_grafana_dashboard()
    print("JMeter and Grafana contour checks passed")


if __name__ == "__main__":
    main()
