#!/usr/bin/env python3
"""Inspect Aula calendar response: compare lessonStatus vs substituteTeacher participants.

Usage:
    PHPSESSID=xxx CSRFP_TOKEN=yyy python scripts/inspect_vikar.py \\
        --profile-id 1878975 --start 2024-08-01 --end 2025-06-30

The cookies must come from a logged-in browser session on www.aula.dk.
Open DevTools -> Application -> Cookies, and copy PHPSESSID and Csrfp-Token.
"""
import argparse
import json
import os
import sys
from collections import Counter

import requests

API_URL = "https://www.aula.dk/api/v22/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) "
    "Gecko/20100101 Firefox/135.0"
)


def fetch(profile_id, start, end, phpsessid, csrf):
    session = requests.Session()
    session.cookies.set("PHPSESSID", phpsessid, domain="www.aula.dk", path="/")
    session.cookies.set("Csrfp-Token", csrf, domain="www.aula.dk", path="/")

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Csrfp-Token": csrf,
        "Origin": "https://www.aula.dk",
        "Referer": "https://www.aula.dk/portal/",
        "Content-Type": "application/json",
    }

    body = {
        "instProfileIds": [int(profile_id)],
        "resourceIds": [],
        "start": f"{start} 00:00:00.0000+01:00",
        "end": f"{end} 23:59:59.9990+01:00",
    }

    url = API_URL + "?method=calendar.getEventsByProfileIdsAndResourceIds"
    r = session.post(url, headers=headers, data=json.dumps(body), timeout=30)
    r.raise_for_status()
    return r.json()


def extract_lessons(payload, profile_id):
    rows = []
    for c in payload.get("data") or []:
        if c.get("type") != "lesson":
            continue
        belongs = c.get("belongsToProfiles") or []
        if belongs and int(belongs[0]) != int(profile_id):
            continue
        lesson = c.get("lesson") or {}
        status = lesson.get("lessonStatus")
        participants = lesson.get("participants") or []
        roles = [p.get("participantRole") for p in participants]
        rows.append({
            "id": c.get("id") or lesson.get("id"),
            "date": (c.get("startDateTime") or "")[:10],
            "title": c.get("title"),
            "lessonStatus": status,
            "roles": roles,
            "has_substituteTeacher": "substituteTeacher" in roles,
        })
    return rows


def report(rows):
    total = len(rows)
    print(f"Total lessons: {total}\n")
    if not total:
        return

    print("== lessonStatus distribution ==")
    for k, v in Counter(r["lessonStatus"] for r in rows).most_common():
        print(f"  {k!r:<25} {v:>5}  ({v/total*100:5.1f}%)")
    print()

    role_counts = Counter()
    for r in rows:
        role_counts.update(r["roles"])
    print("== participantRole distribution (across all participants) ==")
    for k, v in role_counts.most_common():
        print(f"  {k!r:<25} {v:>5}")
    print()

    sub_status = sum(1 for r in rows if r["lessonStatus"] == "substitute")
    sub_role = sum(1 for r in rows if r["has_substituteTeacher"])
    sub_both = sum(
        1 for r in rows if r["lessonStatus"] == "substitute" and r["has_substituteTeacher"]
    )
    print("== Vikar-tællinger sammenlignet ==")
    print(f"  lessonStatus == 'substitute':                {sub_status}")
    print(f"  has substituteTeacher participant:           {sub_role}")
    print(f"  begge dele samtidig:                         {sub_both}")
    print(f"  kun lessonStatus (uden substituteTeacher):   {sub_status - sub_both}")
    print(f"  kun substituteTeacher (status != substitute):{sub_role - sub_both}")
    print()

    only_status = [r for r in rows if r["lessonStatus"] == "substitute" and not r["has_substituteTeacher"]]
    only_role = [r for r in rows if r["lessonStatus"] != "substitute" and r["has_substituteTeacher"]]

    if only_status:
        print(f"== Eksempler: lessonStatus=substitute MEN ingen substituteTeacher (op til 5) ==")
        for r in only_status[:5]:
            print(f"  {r['date']}  {r['title']!r:<40} roles={r['roles']}")
        print()

    if only_role:
        print(f"== Eksempler: substituteTeacher MEN status != substitute (op til 5) ==")
        for r in only_role[:5]:
            print(f"  {r['date']}  {r['title']!r:<40} status={r['lessonStatus']!r} roles={r['roles']}")
        print()


def main():
    p = argparse.ArgumentParser(
        description="Compare Aula lessonStatus vs participantRole=substituteTeacher.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--profile-id", required=True, help="instProfileId for child")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--phpsessid", default=os.environ.get("PHPSESSID"))
    p.add_argument("--csrf", default=os.environ.get("CSRFP_TOKEN"))
    p.add_argument("--dump", help="Write raw JSON response to this path")
    args = p.parse_args()

    if not args.phpsessid or not args.csrf:
        sys.exit(
            "ERROR: Set PHPSESSID and CSRFP_TOKEN env vars, or pass --phpsessid / --csrf.\n"
            "Hent dem fra browser DevTools -> Application -> Cookies paa www.aula.dk."
        )

    payload = fetch(args.profile_id, args.start, args.end, args.phpsessid, args.csrf)
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"Raw response written to {args.dump}\n")

    rows = extract_lessons(payload, args.profile_id)
    report(rows)


if __name__ == "__main__":
    main()
