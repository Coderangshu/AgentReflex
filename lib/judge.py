"""Test coverage and execution judge using Laya."""

from lib.client import query_laya


def judge_test_coverage(code_or_diff: str) -> dict:
    """Evaluate if code changes introduce untested logic or need test coverage.

    Returns dict with evaluation results.
    """
    questions = {
        "needs_tests": {
            "type": "noul",
            "instructions": "Does this code change introduce new business logic, endpoints, or state mutations that require unit/integration test coverage?",
        },
        "is_test_file": {
            "type": "noul",
            "instructions": "Is this code content directly part of a test suite, assertion, or test fixture?",
        },
    }
    res = query_laya(code_or_diff, questions)
    needs_tests = res.get("needs_tests", {}).get("noul", 0.0)
    is_test = res.get("is_test_file", {}).get("noul", 0.0)

    # If it's a test file, it doesn't need additional tests
    uncovered_risk = max(0.0, needs_tests - (is_test * 0.8))

    return {
        "needs_tests_score": needs_tests,
        "is_test_file_score": is_test,
        "uncovered_risk": uncovered_risk,
        "requires_verification": uncovered_risk >= 0.70,
    }
