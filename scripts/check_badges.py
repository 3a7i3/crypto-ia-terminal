import sys

import requests

BADGES = [
    {
        "name": "Codecov",
        "url": "https://codecov.io/gh/3a7i3/crypto-ia-terminal/branch/main/graph/badge.svg",
    },
    {
        "name": "Coveralls",
        "url": "https://coveralls.io/repos/github/3a7i3/crypto-ia-terminal/badge.svg?branch=main",
    },
]


def check_badge(badge):
    print(f"Checking {badge['name']} badge...")
    r = requests.get(badge["url"])
    if r.status_code == 200 and b"svg" in r.content:
        print(f"  [OK] Badge SVG accessible: {badge['url']}")
    else:
        print(f"  [FAIL] Badge not accessible or not SVG: {badge['url']}")
        sys.exit(1)


if __name__ == "__main__":
    for badge in BADGES:
        check_badge(badge)
    print("All badges are accessible and valid.")
