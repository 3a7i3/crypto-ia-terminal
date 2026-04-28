import sys

import requests

BADGES = [
    {
        "name": "Codecov",
        "url": "https://codecov.io/gh/0xl1v/crypto-ai-terminal/branch/main/graph/badge.svg",
        "page": "https://codecov.io/gh/0xl1v/crypto-ai-terminal",
    },
    {
        "name": "Coveralls",
        "url": "https://coveralls.io/repos/github/0xl1v/crypto-ai-terminal/badge.svg?branch=main",
        "page": "https://coveralls.io/github/0xl1v/crypto-ai-terminal?branch=main",
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
    r2 = requests.get(badge["page"])
    if r2.status_code == 200:
        print(f"  [OK] Badge page accessible: {badge['page']}")
    else:
        print(f"  [FAIL] Badge page not accessible: {badge['page']}")
        sys.exit(1)


if __name__ == "__main__":
    for badge in BADGES:
        check_badge(badge)
    print("All badges are accessible and valid.")
