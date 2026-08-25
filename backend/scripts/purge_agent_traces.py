"""Daily maintenance entry point for the trace retention policy."""

from app.services.agent_traces import enforce_trace_retention


if __name__ == "__main__":
    enforce_trace_retention()
    print("Agent trace retention enforced")
