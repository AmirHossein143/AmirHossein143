#!/usr/bin/env python3
"""
Fetch real GitHub stats (authenticated, so no rate-limit problems) and render
them into github-stats.svg using assets/stats-template.svg as the template.

Environment variables:
  GH_TOKEN     - a GitHub token (Personal Access Token recommended). Required.
  GH_USERNAME  - the GitHub username to report on. Required.

Counts PUBLIC repositories and PUBLIC stars (what visitors can verify).
Total commits uses GitHub's commit-search index (public commits authored by you).
Total contributions sums your contribution calendar across every year.
"""

import os
import sys
import json
import datetime
import urllib.request
import urllib.error

TOKEN = os.environ.get("GH_TOKEN")
USER = os.environ.get("GH_USERNAME")

if not TOKEN or not USER:
    sys.exit("ERROR: GH_TOKEN and GH_USERNAME environment variables are required.")

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"bearer {TOKEN}",
    "User-Agent": USER,
}


def graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        f"{API}/graphql",
        data=body,
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]


def rest(path):
    req = urllib.request.Request(
        f"{API}{path}",
        headers={**HEADERS, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def get_repos_and_stars(login):
    """Public owned repos: total count + summed stargazers."""
    stars = 0
    total = 0
    created = None
    cursor = None
    query = """
    query($login:String!, $cursor:String){
      user(login:$login){
        createdAt
        repositories(ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false,
                     first:100, after:$cursor){
          totalCount
          nodes { stargazerCount }
          pageInfo { hasNextPage endCursor }
        }
      }
    }"""
    while True:
        data = graphql(query, {"login": login, "cursor": cursor})
        user = data["user"]
        created = user["createdAt"]
        repos = user["repositories"]
        total = repos["totalCount"]
        for node in repos["nodes"]:
            stars += node["stargazerCount"]
        if repos["pageInfo"]["hasNextPage"]:
            cursor = repos["pageInfo"]["endCursor"]
        else:
            break
    return total, stars, created


def get_total_commits(login):
    """All public commits authored by the user (matches 'include_all_commits')."""
    try:
        data = rest(f"/search/commits?q=author:{login}&per_page=1")
        return data.get("total_count", 0)
    except urllib.error.HTTPError as e:
        print(f"WARN: commit search failed ({e.code}); defaulting to 0", file=sys.stderr)
        return 0


def get_total_contributions(login, created_at):
    """Sum the contribution calendar across every year since account creation."""
    start_year = int(created_at[:4])
    now = datetime.datetime.now(datetime.timezone.utc).year
    total = 0
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!){
      user(login:$login){
        contributionsCollection(from:$from, to:$to){
          contributionCalendar { totalContributions }
        }
      }
    }"""
    for year in range(start_year, now + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to = f"{year}-12-31T23:59:59Z"
        data = graphql(query, {"login": login, "from": frm, "to": to})
        total += data["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    return total


def main():
    print(f"Fetching stats for {USER} ...")
    repos, stars, created = get_repos_and_stars(USER)
    commits = get_total_commits(USER)
    contribs = get_total_contributions(USER, created)

    print(f"  Repositories : {repos}")
    print(f"  Stars        : {stars}")
    print(f"  Commits      : {commits}")
    print(f"  Contributions: {contribs}")

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    template_path = os.path.join(root, "assets", "stats-template.svg")
    output_path = os.path.join(root, "github-stats.svg")

    with open(template_path, encoding="utf-8") as f:
        svg = f.read()

    svg = (svg
           .replace("{{STARS}}", f"{stars:,}")
           .replace("{{COMMITS}}", f"{commits:,}")
           .replace("{{REPOS}}", f"{repos:,}")
           .replace("{{CONTRIBS}}", f"{contribs:,}"))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
