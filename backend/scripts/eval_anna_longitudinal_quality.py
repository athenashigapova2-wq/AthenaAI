"""Backward-compatible entry point for the generic live evaluator."""

from eval_longitudinal_quality import main, run

__all__ = ["main", "run"]


if __name__ == "__main__":
    raise SystemExit(main())
