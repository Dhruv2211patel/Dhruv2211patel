#!/usr/bin/env python3

import argparse
import json
import os
import urllib.request
from datetime import datetime
from html import escape
from pathlib import Path


GRAPHQL_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    repositories(privacy: PUBLIC) {
      totalCount
    }
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_activity(username: str, token: str) -> dict:
    now = datetime.utcnow()
    try:
        start = now.replace(year=now.year - 1)
    except ValueError:
        start = now.replace(year=now.year - 1, day=28)

    payload = json.dumps(
        {
            "query": GRAPHQL_QUERY,
            "variables": {
                "login": username,
                "from": start.strftime("%Y-%m-%dT00:00:00Z"),
                "to": now.strftime("%Y-%m-%dT23:59:59Z"),
            },
        }
    ).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "github-profile-activity-card",
        },
    )
    with urllib.request.urlopen(request) as response:
        result = json.load(response)

    if result.get("errors"):
        raise RuntimeError(result["errors"])
    return result["data"]["user"]


def build_svg(username: str, user: dict) -> str:
    calendar = user["contributionsCollection"]["contributionCalendar"]
    weeks = calendar["weeks"]
    weekly_counts = [
        sum(day["contributionCount"] for day in week["contributionDays"])
        for week in weeks
    ]
    active_weeks = sum(count > 0 for count in weekly_counts)
    total = calendar["totalContributions"]
    public_repos = user["repositories"]["totalCount"]

    width, height = 1000, 330
    chart_x, chart_y = 42, 125
    chart_width, chart_height = 916, 130
    step = chart_width / max(len(weekly_counts) - 1, 1)
    maximum = max(max(weekly_counts, default=0), 1)
    points = []
    circles = []

    for index, count in enumerate(weekly_counts):
        x = chart_x + index * step
        y = chart_y + chart_height - (count / maximum) * chart_height
        points.append(f"{x:.1f},{y:.1f}")
        if count:
            circles.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#ffffff" '
                f'stroke="#58a6ff" stroke-width="3"><title>{count} contributions</title></circle>'
            )

    baseline = chart_y + chart_height
    area_points = f"{chart_x},{baseline} " + " ".join(points) + f" {chart_x + chart_width},{baseline}"

    month_labels = []
    previous_month = None
    for index, week in enumerate(weeks):
        days = week["contributionDays"]
        if not days:
            continue
        date = datetime.strptime(days[0]["date"], "%Y-%m-%d")
        if date.month != previous_month:
            x = chart_x + index * step
            month_labels.append(
                f'<text x="{x:.1f}" y="282" class="axis">{date.strftime("%b")}</text>'
            )
            previous_month = date.month

    grid_lines = []
    for fraction in (0, 0.5, 1):
        y = chart_y + chart_height * fraction
        grid_lines.append(
            f'<line x1="{chart_x}" y1="{y:.1f}" x2="{chart_x + chart_width}" y2="{y:.1f}" class="grid" />'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="330" viewBox="0 0 1000 330" role="img" aria-label="{escape(username)} public GitHub activity">
  <defs>
    <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#58a6ff" stop-opacity="0.45" />
      <stop offset="100%" stop-color="#58a6ff" stop-opacity="0.03" />
    </linearGradient>
  </defs>
  <style>
    .title {{ fill: #f0f6fc; font: 700 20px ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .subtitle {{ fill: #8b949e; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .metric {{ fill: #58a6ff; font: 700 25px ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .metric-label {{ fill: #8b949e; font: 11px ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .axis {{ fill: #8b949e; font: 11px ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .grid {{ stroke: #21262d; stroke-width: 1; }}
  </style>
  <rect x="1" y="1" width="998" height="328" rx="14" fill="#0d1117" stroke="#30363d" stroke-width="2" />
  <text x="42" y="42" class="title">PUBLIC GITHUB ACTIVITY</text>
  <text x="42" y="65" class="subtitle">{escape(username)} · rolling 12-month timeline</text>

  <text x="612" y="43" class="metric">{total}</text>
  <text x="612" y="62" class="metric-label">CONTRIBUTIONS</text>
  <text x="748" y="43" class="metric">{active_weeks}</text>
  <text x="748" y="62" class="metric-label">ACTIVE WEEKS</text>
  <text x="866" y="43" class="metric">{public_repos}</text>
  <text x="866" y="62" class="metric-label">PUBLIC REPOS</text>

  {''.join(grid_lines)}
  <polygon points="{area_points}" fill="url(#area)" />
  <polyline points="{' '.join(points)}" fill="none" stroke="#58a6ff" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" />
  {''.join(circles)}
  {''.join(month_labels)}
  <text x="958" y="312" text-anchor="end" class="subtitle">build → ship → iterate</text>
</svg>
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=os.getenv("GITHUB_USERNAME", "Dhruv2211patel"))
    parser.add_argument("--output", default="assets/github-activity.svg")
    parser.add_argument("--input")
    args = parser.parse_args()

    if args.input:
        raw = json.loads(Path(args.input).read_text())
        user = raw.get("data", {}).get("user", raw)
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is required when --input is not supplied")
        user = fetch_activity(args.username, token)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_svg(args.username, user))


if __name__ == "__main__":
    main()
