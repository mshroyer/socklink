#!/bin/env python3

"""Runs the SourceHut builds

Submits the builds under the manifests/ directory to SourceHut, then waits for
them to all complete.  If any builds fail, cancels any still running and then
exits with a nonzero status.

"""

import asyncio
from textwrap import dedent
import os

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
import requests


ENDPOINT = "https://builds.sr.ht/query"


class SourceHutClient:
    """An authenticated SourceHut client"""

    repo_url: str
    _token: str

    def __init__(self, repo_url: str, token: str):
        self.repo_url = repo_url
        self._token = token

    async def submit_build(self, manifest: str) -> int:
        """Submits a build manifest provided as YAML

        Returns its build number.

        """

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "tsock/ci",
        }

        transport = AIOHTTPTransport("https://builds.sr.ht/query", headers=headers)
        client = Client(transport=transport)

        query = gql("""
          mutation submit ($manifest: String!, $tags: [String!], $note: String, $visibility: Visibility, $secrets: Boolean!) {
            submit(manifest: $manifest, tags: $tags, note: $note, visibility: $visibility, secrets: $secrets) {
              id
              owner {
                canonicalName
              }
            }
          }
        """)

        query.variable_values = {
            "manifest": manifest,
            "note": "Submitted via GraphQL",
            "secrets": True,
            "tags": ["api-test"],
            "visibility": "UNLISTED",
        }

        async with client as session:
            result = await session.execute(query)

        return result["submit"]["id"]

    def submit_build_with_requests(self, manifest: str) -> int:
        """Submits a build manifest provided as YAML

        Returns its build number.

        """

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "tsock/ci",
        }

        # Debug mutation:
        # {{"query":"mutation submit ($manifest: String!, $tags: [String!], $note: String, $visibility: Visibility, $secrets: Boolean!) {\n\tsubmit(manifest: $manifest, tags: $tags, note: $note, visibility: $visibility, secrets: $secrets) {\n\t\tid\n\t\towner {\n\t\t\tcanonicalName\n\t\t}\n\t}\n}\n","variables":{"manifest":"image: archlinux\npackages:\n  - python\n  - tmux\nsources:\n  - https://github.com/mshroyer/tsock\ntasks:\n  - test: |\n      cd tsock\n      ./scripts/test.sh\n","note":"","secrets":true,"tags":[""],"visibility":"UNLISTED"}}}

        submit_mutation = dedent("""\
        {
          {
            "query": "mutation submit ($manifest: String!, $tags: [String!], $note: String, $visibility: Visibility, $secrets: Boolean!) {
            submit(manifest: $manifest, tags: $tags, note: $note, visibility: $visibility, secrets: $secrets) {
              id
              owner {
                canonicalName
              }
            }
          }",
          "variables": {
            "manifest": "image: archlinux\npackages:\n  - python\n  - tmux\nsources:\n  - https://github.com/mshroyer/tsock\ntasks:\n  - test: |\n      cd tsock\n      ./scripts/test.sh\n",
            "note": "api-test",
            "secrets": true,
            "tags": [""],
            "visibility":"UNLISTED"
          }
        }
        """)

        mutation = dedent(r"""\
            mutation submit ($manifest: String!, $tags: [String!], $note: String, $visibility: Visibility, $secrets: Boolean!) {
              submit(manifest: $manifest, tags: $tags, note: $note, visibility: $visibility, secrets: $secrets) {
                id
                owner {
                  canonicalName
                }
              }
            }""")

        variables = {
            "manifest": manifest,
            "note": "Submitted via GraphQL",
            "secrets": True,
            "tags": ["api-test"],
            "visibility": "UNLISTED",
        }

        json = {
            "query": mutation,
            "variables": variables,
        }

        import http.client
        import logging

        http.client.HTTPConnection.debuglevel = 1
        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True

        r = requests.post(
            ENDPOINT,
            json=json,
            headers=headers,
        )
        r.raise_for_status()

        job = r.json()["data"]["submit"]
        job_id = job["id"]
        return job_id


async def main():
    token = os.getenv("SOURCEHUT_ACCESS_TOKEN")
    if token is None:
        raise ValueError("SOURCEHUT_ACCESS_TOKEN not set")

    client = SourceHutClient("https://github.com/mshroyer/tsock", token)
    build_id = await client.submit_build(
        dedent("""\
        image: archlinux
        packages:
          - python
          - tmux
        sources:
          - https://github.com/mshroyer/tsock
        tasks:
          - test: |
              cd tsock
              ./scripts/test.sh
        """)
    )
    print(f"build_id = {build_id}")


if __name__ == "__main__":
    asyncio.run(main())
