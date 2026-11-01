"""Check invented ambiguity examples only; no admission or market data."""

import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "docs/research/market_time_attestation_546/interval_reference.py"


def verify(document):
    if (
        document.get("synthetic") is not True
        or document.get("admission_granted") is not False
    ):
        raise ValueError("SYNTHETIC_NO_ADMISSION_REQUIRED")
    expected = {
        "UNBOUNDED_SOURCE_OFFSET",
        "UNBOUNDED_EVENT_TO_LABEL_DELAY",
        "CONSISTENT_SAMPLES_WITH_CONSTANT_OFFSET",
    }
    examples = document["examples"]
    if len(examples) != 3 or {x["id"] for x in examples} != expected:
        raise ValueError("COMPLETE_SYNTHETIC_POPULATION_REQUIRED")
    if any(len(x["worlds"]) != 2 for x in examples):
        raise ValueError("TWO_SYNTHETIC_WORLDS_REQUIRED")
    model = runpy.run_path(str(REFERENCE))
    Span, Window = model["Span"], model["Window"]
    checked = 0
    for example in document["examples"]:
        observed = example["observed"]
        if example["kind"] == "event":
            ages = []
            for world in example["worlds"]:
                assumptions = world["assumptions"]
                event = model["event_window"](
                    observed["native_ns"],
                    offset=Span(*assumptions["offset_ns"]),
                    quantization=Span(*observed["quantization_ns"]),
                    event_to_stamp_lag=Span(*assumptions["lag_ns"]),
                    scale="SYNTHETIC_COMMON",
                )
                age = model["age_window"](
                    Window(
                        "SYNTHETIC_COMMON", Span(observed["now_ns"], observed["now_ns"])
                    ),
                    event,
                )
                if [event.span.lo, event.span.hi] != world["expected_event_ns"]:
                    raise ValueError("SYNTHETIC_EVENT_MISMATCH")
                if [age.lo, age.hi] != world["expected_age_ns"]:
                    raise ValueError("SYNTHETIC_AGE_MISMATCH")
                ages.append(age)
                checked += 1
            if len(set(ages)) < 2:
                raise ValueError("AMBIGUITY_NOT_DEMONSTRATED")
        elif example["kind"] == "clock_stability":
            wall, mono = observed["wall_ns"], observed["monotonic_ns"]
            for value in wall + mono:
                model["integer"](value)
            residuals = [
                abs((v - wall[0]) - (u - mono[0]))
                for v, u in zip(wall, mono, strict=True)
            ]
            if max(residuals) != example["expected_max_delta_difference_ns"]:
                raise ValueError("SYNTHETIC_RESIDUAL_MISMATCH")
            offsets = [w["assumed_constant_offset_ns"] for w in example["worlds"]]
            if len(set(offsets)) < 2:
                raise ValueError("DISTINCT_SYNTHETIC_OFFSETS_REQUIRED")
            for offset in offsets:
                model["integer"](offset)
                common = [v - offset for v in wall]
                if [v - common[0] for v in common] != [v - wall[0] for v in wall]:
                    raise ValueError("SYNTHETIC_OFFSET_CANCELLATION_MISMATCH")
                checked += 1
        else:
            raise ValueError("UNKNOWN_SYNTHETIC_EXAMPLE")
    return {"synthetic_worlds_checked": checked, "admission_granted": False}


if __name__ == "__main__":
    data = json.loads(
        Path(__file__).with_name("SYNTHETIC_COUNTEREXAMPLES.json").read_text()
    )
    print(json.dumps(verify(data), indent=2, sort_keys=True))
