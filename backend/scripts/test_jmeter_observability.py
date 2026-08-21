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


def check_grafana_dashboard() -> None:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
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


def main() -> None:
    check_jmeter_plan()
    check_grafana_dashboard()
    print("JMeter and Grafana contour checks passed")


if __name__ == "__main__":
    main()
