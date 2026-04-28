# Auto-generated test report for all modules
#
# This file is overwritten at each test run.

import os
from datetime import datetime


def parse_pytest_output(output_path):
    if not os.path.exists(output_path):
        return "No test output found."
    with open(output_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    summary = []
    errors = []
    in_error = False
    for line in lines:
        if "====" in line and (
            "failed" in line or "passed" in line or "skipped" in line
        ):
            summary.append(line.strip())
        if line.startswith("E   "):
            in_error = True
            errors.append(line.strip())
        elif in_error and line.strip() == "":
            in_error = False
    return "\n".join(summary) + ("\n\nErrors:\n" + "\n".join(errors) if errors else "")


def generate_report():
    output_path = "all_tests_output2.txt"
    report_path = "test_report.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = parse_pytest_output(output_path)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Test Report\n\n")
        f.write(f"**Date:** {now}\n\n")
        f.write("## Résumé\n")
        f.write(summary or "Aucun résultat trouvé.")
    print(f"Test report generated: {report_path}")


if __name__ == "__main__":
    generate_report()
