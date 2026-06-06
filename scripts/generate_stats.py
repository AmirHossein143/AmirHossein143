#!/usr/bin/env python3
"""
Fetch real GitHub stats via authenticated GraphQL (no rate-limit issues) and
render them into github-stats.svg using assets/stats-template.svg.

Environment variables:
  GH_TOKEN     - Personal Access Token (classic, read:user scope). Required.
  GH_USERNAME  - GitHub username to report on. Required.

Stat definitions
  Total Stars         - sum of stargazerCount across public owned repos
  Total Commits       - sum of totalCommitContributions across all years
                        (same source as GitHub's contribution graph — accurate)
  Total Repositories  - count of public owned non-fork repos
  Total Contributions - sum of contributionCalendar.totalContributions per year
                        (commits + PRs + issues + reviews combined)
"""

import os
import sys
import json
import datetime
import urllib.request

TOKEN    = os.environ.get("GH_TOKEN")
USER     = os.environ.get("GH_USERNAME")

if not TOKEN or not USER:
    sys.exit("ERROR: GH_TOKEN and GH_USERNAME environment variables are required.")

API     = "https://api.github.com"
HEADERS = {"Authorization": f"bearer {TOKEN}", "User-Agent": USER}


def graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req  = urllib.request.Request(
        f"{API}/graphql",
        data=body,
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]


# ── 1. Repos, stars, account creation year ───────────────────────────────────

def get_repos_and_stars(login):
    stars, total, created = 0, 0, None
    cursor = None
    query = """
    query($login:String!, $cursor:String){
      user(login:$login){
        createdAt
        repositories(ownerAffiliations:OWNER, privacy:PUBLIC,
                     isFork:false, first:100, after:$cursor){
          totalCount
          nodes { stargazerCount }
          pageInfo { hasNextPage endCursor }
        }
      }
    }"""
    while True:
        data  = graphql(query, {"login": login, "cursor": cursor})
        user  = data["user"]
        created = user["createdAt"]
        repos = user["repositories"]
        total = repos["totalCount"]
        stars += sum(n["stargazerCount"] for n in repos["nodes"])
        if repos["pageInfo"]["hasNextPage"]:
            cursor = repos["pageInfo"]["endCursor"]
        else:
            break
    return total, stars, created


# ── 2. Commits + contributions — one GraphQL call per year ───────────────────
#
# totalCommitContributions  = commits to repos' default branches that year
#   (same data source as the contribution graph — far more accurate than
#    the search API which only indexes a subset of public commits)
#
# contributionCalendar.totalContributions = commits + PRs + issues + reviews

def get_commits_and_contributions(login, created_at):
    start_year = int(created_at[:4])
    now        = datetime.datetime.now(datetime.timezone.utc).year
    total_commits = 0
    total_contribs = 0

    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!){
      user(login:$login){
        contributionsCollection(from:$from, to:$to){
          totalCommitContributions
          contributionCalendar { totalContributions }
        }
      }
    }"""

    for year in range(start_year, now + 1):
        frm  = f"{year}-01-01T00:00:00Z"
        to   = f"{year}-12-31T23:59:59Z"
        data = graphql(query, {"login": login, "from": frm, "to": to})
        col  = data["user"]["contributionsCollection"]
        total_commits  += col["totalCommitContributions"]
        total_contribs += col["contributionCalendar"]["totalContributions"]

    return total_commits, total_contribs


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Fetching stats for {USER} ...")
    repos, stars, created   = get_repos_and_stars(USER)
    commits, contribs       = get_commits_and_contributions(USER, created)

    print(f"  Repositories : {repos}")
    print(f"  Stars        : {stars}")
    print(f"  Commits      : {commits}")
    print(f"  Contributions: {contribs}")

    here     = os.path.dirname(os.path.abspath(__file__))
    root     = os.path.dirname(here)
    template = os.path.join(root, "assets", "stats-template.svg")
    output   = os.path.join(root, "github-stats.svg")

    with open(template, encoding="utf-8") as f:
        svg = f.read()

    svg = (svg
           .replace("{{STARS}}",   f"{stars:,}")
           .replace("{{COMMITS}}", f"{commits:,}")
           .replace("{{REPOS}}",   f"{repos:,}")
           .replace("{{CONTRIBS}}", f"{contribs:,}"))

    with open(output, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Wrote {output}")


if __name__ == "__main__":
    main()