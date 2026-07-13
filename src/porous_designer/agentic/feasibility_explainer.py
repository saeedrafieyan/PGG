"""Readable explanations that preserve deterministic feasibility status."""

from __future__ import annotations


class FeasibilityExplainer:
    def explain(self, deterministic_result: dict, approved_specification: dict) -> str:
        status = deterministic_result.get("status", "unknown")
        memory = deterministic_result.get("peak_memory_gb") or deterministic_result.get("estimated_peak_memory_gb")
        parts = [f"The deterministic feasibility status is {status}."]
        if memory is not None:
            parts.append(f"Estimated peak memory is approximately {float(memory):.2f} GB.")
        formats = approved_specification.get("export", {}).get("formats", [])
        if "step" in formats:
            parts.append("STEP was requested, but validated production output remains STL-only in this phase.")
        if status == "infeasible":
            parts.append("The request remains infeasible unless deterministic inputs are changed and re-estimated.")
        return " ".join(parts)
