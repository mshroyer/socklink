#!/usr/bin/env python3

"""Lints and automation for creating releases

Makes sure version numbers and CHANGELOG entries are valid, and that all tests
have passed, before creating a release.

Forked from the original version at
https://github.com/mshroyer/coursepointer/

"""

import argparse
from enum import Enum
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import List, Optional


CI_WORKFLOWS = ["lint", "test-macos", "test-ubuntu"]


def last_changelog_version() -> Optional[str]:
    pattern = re.compile(r"^## v(\d+\.\d+\.\d+)")
    with open("CHANGELOG.md") as f:
        for line in f:
            m = pattern.match(line)
            if m:
                return m.group(1)
    return None


def is_checkout_unmodified() -> bool:
    output = subprocess.check_output(
        ["git", "status", "--porcelain"], universal_newlines=True
    ).strip()
    return len(output) == 0


def rev_parse(rev: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", rev],
        universal_newlines=True,
    ).strip()


def read_tag(tag: str) -> str:
    return rev_parse(f"tags/{tag}")


def get_tags_at(rev: str) -> List[str]:
    output = subprocess.check_output(
        ["git", "tag", "--points-at", rev],
        universal_newlines=True,
    ).strip()
    return output.splitlines()


def get_tagged_version(rev: str) -> Optional[str]:
    pattern = re.compile(r"^v(\d+\.\d+\.\d+)$")
    for tag in get_tags_at(rev):
        m = pattern.match(tag)
        if m is not None:
            return m.group(1)
    return None


def read_head() -> str:
    return rev_parse("HEAD")


def _get_gh_json(key: str, query: str) -> str:
    return (
        subprocess.check_output(
            [
                "gh",
                "repo",
                "view",
                "--json",
                key,
                "-q",
                query,
            ]
        )
        .decode("utf-8")
        .rstrip()
    )


def get_github_repo_name() -> str:
    owner = _get_gh_json("owner", ".owner.login")
    name = _get_gh_json("name", ".name")
    return f"{owner}/{name}"


def query_ci_runs(workflow: str, sha: str) -> dict:
    output = subprocess.check_output(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2022-11-28",
            f"/repos/{get_github_repo_name()}/actions/workflows/{workflow}.yml/runs?head_sha={sha}",
        ]
    )

    runs = json.loads(output)
    return runs["workflow_runs"]


def successful_run_id(workflow_runs: dict) -> Optional[int]:
    for run in workflow_runs:
        if (
            run["status"] == "completed"
            and run["conclusion"] == "success"
            and run["event"] == "push"
        ):
            return run["id"]
    return None


def pending_run_id(workflow_runs: dict) -> Optional[int]:
    for run in workflow_runs:
        if (
            run["status"]
            in ("expected", "in_progress", "pending", "queued", "requested", "waiting")
            and run["event"] == "push"
        ):
            return run["id"]
        return None


class CiStatus(Enum):
    UNKNOWN = 0
    PENDING = 1
    SUCCESS = 2
    FAILURE = 3


def get_combined_ci_status(sha: str) -> CiStatus:
    result = CiStatus.SUCCESS
    for workflow in CI_WORKFLOWS:
        runs = query_ci_runs(workflow, sha)
        if successful_run_id(runs) is not None:
            continue
        elif pending_run_id(runs) is not None:
            result = CiStatus.PENDING
        else:
            return CiStatus.FAILURE

    return result


def lint(args: argparse.Namespace):
    if not is_checkout_unmodified():
        print("Git checkout is modified!", file=sys.stderr)
        sys.exit(1)

    version = get_tagged_version("HEAD")
    if version is None:
        print("HEAD has no tagged version", file=sys.stderr)
        sys.exit(1)

    if last_changelog_version() != version:
        print("CHANGELOG is not up-to-date!", file=sys.stderr)
        sys.exit(1)

    print("Release lint check successful.")


def wait_ci(args: argparse.Namespace):
    max_repeat = 90
    while True:
        # Sleep first to try to prevent racing against the CI workflow being
        # queued.
        time.sleep(10)

        status = get_combined_ci_status(args.hash)
        if status == CiStatus.SUCCESS:
            print(f"Found successful CI runs for commit {args.hash}")
            return

        if status == CiStatus.FAILURE:
            print(
                f"No successful or pending CI runs for commit {args.hash}",
                file=sys.stderr,
            )
            sys.exit(1)

        if max_repeat == 0:
            print(f"Timed out waiting for CI runs for commit {args.hash}")
            sys.exit(1)

        print(f"Waiting on CI runs for commit {args.hash}")
        max_repeat -= 1


def create(args: argparse.Namespace):
    version = get_tagged_version("HEAD")
    if version is None:
        print("No release version is tagged", file=sys.stderr)
        sys.exit(1)

    with open("CHANGELOG.md") as r:
        with open("release_notes.md", "w") as w:
            current_version = False
            past_padding = False
            for line in r:
                if current_version:
                    if line.startswith("## "):
                        break

                    if line.strip() != "":
                        past_padding = True
                    if past_padding:
                        print(line.strip(), file=w)
                elif line.strip() == f"## v{version}":
                    current_version = True

    subprocess.run(
        [
            "gh",
            "release",
            "create",
            f"v{version}",
            "--title",
            f"v{version}",
            "--notes-file",
            "release_notes.md",
            "--draft",
            "--verify-tag",
        ],
        check=True,
    )


def upload(args: argparse.Namespace):
    version = get_tagged_version("HEAD")
    subprocess.run(
        ["gh", "release", "upload", "--clobber", f"v{version}", args.file], check=True
    )


def head(args: argparse.Namespace):
    version = get_tagged_version("HEAD")
    if version is None:
        print("No currently tagged version number at HEAD", file=sys.stderr)
        sys.exit(1)
    print(version)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--repo", help="GitHub repository name, e.g. 'mshroyer/coursepointer'"
    )
    subparsers = parser.add_subparsers(help="Subcommand")

    parser_lint = subparsers.add_parser("lint", help="Lint the release")
    parser_lint.set_defaults(func=lint)

    parser_wait = subparsers.add_parser(
        "wait-ci", help="Wait for CI to complete for a commit"
    )
    parser_wait.set_defaults(func=wait_ci)
    parser_wait.add_argument("hash", type=str, help="Commit hash")

    parser_notes = subparsers.add_parser("create", help="Create a release")
    parser_notes.set_defaults(func=create)

    parser_upload = subparsers.add_parser("upload", help="Upload a release asset")
    parser_upload.set_defaults(func=upload)
    parser_upload.add_argument("file", type=Path, help="File to upload")

    parser_head = subparsers.add_parser("head", help="Show version for release at HEAD")
    parser_head.set_defaults(func=head)

    args = parser.parse_args()
    if "func" not in args:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
