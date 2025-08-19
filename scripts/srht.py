#!/bin/env python3

"""Runs the SourceHut builds

Submits the builds under the manifests/ directory to SourceHut, then waits for
them to all complete.  If any builds fail, cancels any still running and then
exits with a nonzero status.

"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
import pdb
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar
import os

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport


ENDPOINT = "https://builds.sr.ht/query"

POLL_INTERVAL = timedelta(seconds=30)


class JobStatus(Enum):
    """The status of a single job"""

    UNKNOWN = 0
    PENDING = 1
    QUEUED = 2
    RUNNING = 3
    SUCCESS = 4
    FAILED = 5
    TIMEOUT = 6
    CANCELLED = 7

    def is_terminal(self) -> bool:
        return self in (
            JobStatus.SUCCESS,
            JobStatus.FAILED,
            JobStatus.TIMEOUT,
            JobStatus.CANCELLED,
        )

    def __str__(self) -> str:
        return str(self.name).upper()

    @classmethod
    def from_str(cls, s: str) -> "JobStatus":
        return cls.__members__[s]


class Visibility(Enum):
    """Visibility specification for a job"""

    PUBLIC = 1
    PRIVATE = 2
    UNLISTED = 3

    def __str__(self) -> str:
        return str(self.name).upper()


@dataclass
class Job:
    """A build job"""

    job_id: int
    canonical_name: str
    status: JobStatus

    def url(self) -> str:
        """Returns the URL of the build's status page"""
        return f"https://builds.sr.ht/{self.canonical_name}/jobs/{self.job_id}"


@dataclass
class JobGroup:
    group_id: int
    jobs: List[Job]
    canonical_name: str


class SourceHutClient:
    """An authenticated SourceHut client"""

    repo_url: str
    _token: str
    _client: Client

    def __init__(self, repo_url: str, token: str):
        self.repo_url = repo_url
        self._token = token
        self._client = self._make_client()

    def _make_client(self) -> Client:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "tsock/srht.py",
        }
        transport = AIOHTTPTransport("https://builds.sr.ht/query", headers=headers)
        return Client(transport=transport)

    async def submit_job(
        self,
        manifest: str,
        note: str = "",
        tags: List[str] = list(),
        visibility: Visibility = Visibility.UNLISTED,
        execute: bool = True,
    ) -> Job:
        """Submits a build manifest provided as YAML

        If execute is false, the build will not be automatically started.

        Returns its build number.

        """

        query = gql("""
          mutation submit ($manifest: String!, $tags: [String!], $note: String, $execute: Boolean, $visibility: Visibility, $secrets: Boolean!) {
            submit(manifest: $manifest, tags: $tags, note: $note, execute: $execute, visibility: $visibility, secrets: $secrets) {
              id
              owner {
                canonicalName
              }
            }
          }
        """)

        query.variable_values = {
            "manifest": manifest,
            "note": note,
            "secrets": True,
            "tags": tags,
            "execute": execute,
            "visibility": str(visibility),
        }

        async with self._client as session:
            result = await session.execute(query)

        return Job(
            job_id=result["submit"]["id"],
            canonical_name=result["submit"]["owner"]["canonicalName"],
            status=JobStatus.UNKNOWN,
        )

    async def create_group(self, jobs: List[Job], note: str = "", execute: bool = True):
        query = gql("""
          mutation createGroup($jobIds: [Int!]!, $execute: Boolean, $note: String) {
            createGroup(jobIds: $jobIds, execute: $execute, note: $note) {
              id
              owner {
                canonicalName
              }
            }
          }
        """)

        query.variable_values = {
            "jobIds": list(map(lambda j: j.job_id, jobs)),
            "note": note,
            "execute": execute,
        }

        async with self._client as session:
            result = await session.execute(query)

        return JobGroup(
            group_id=result["createGroup"]["id"],
            jobs=jobs,
            canonical_name=result["createGroup"]["owner"]["canonicalName"],
        )

    async def get_job_status(self, job_id: int) -> JobStatus:
        """Returns the current status of the given build ID."""

        query = gql("""
          query job($id: Int!) {
              job(id: $id) {
                  created
                  updated
                  status
              }
          }
        """)

        query.variable_values = {
            "id": job_id,
        }

        async with self._client as session:
            result = await session.execute(query)

        return JobStatus.from_str(result["job"]["status"])


class JobManager:
    _client: SourceHutClient
    _max_concurrency: int

    def __init__(self, client: SourceHutClient, max_concurrency: int = 3):
        self._client = client
        self._max_concurrency = max_concurrency

    async def start_group_from_manifest_dir(self, manifest_dir: Path | str) -> JobGroup:
        """Starts a job group from YAML manifest files in a directory

        Returns the ID of the running group.

        """

        manifest_dir = Path(os.fspath(manifest_dir))
        manifests = []
        for manifest_file in manifest_dir.glob("*.yml"):
            manifests.append(manifest_file.read_text())

        jobs = await _run_with_bounded_concurrency(
            self._max_concurrency,
            lambda m: self._client.submit_job(m, execute=False),
            manifests,
        )
        return await self._client.create_group(jobs, note="")

    async def update_job_statuses(self, jobs: List[Job]) -> List[Job]:
        """Get a list of jobs with updated statuses

        Returns a new list of Jobs with updated status fields.

        """

        return await _run_with_bounded_concurrency(
            self._max_concurrency, self._get_updated_job, jobs
        )

    async def _get_updated_job(self, job: Job) -> Job:
        if job.status.is_terminal():
            return job

        new_status = await self._client.get_job_status(job.job_id)
        return Job(job.job_id, job.canonical_name, new_status)


T = TypeVar("T")
U = TypeVar("U")


async def _run_with_bounded_concurrency(
    max_concurrency: int, fn: Callable[[T], Awaitable[U]], args: List[T]
) -> List[U]:
    """Runs the callables with an upper bound on their concurrency

    We can use this to get some concurrency from our calls to SourceHut job
    management APIs, while avoiding opening an ungemtlemanly number of
    simultaneous requests.

    """

    sem = asyncio.Semaphore(max_concurrency)

    async def runner(arg):
        async with sem:
            return await fn(arg)

    return await asyncio.gather(*(runner(arg) for arg in args))


async def main():
    token = os.getenv("SOURCEHUT_ACCESS_TOKEN")
    if token is None:
        raise ValueError("SOURCEHUT_ACCESS_TOKEN not set")

    client = SourceHutClient("https://github.com/mshroyer/tsock", token)
    manager = JobManager(client)

    # build_id = await client.submit_build(
    #     dedent("""\
    #     image: archlinux
    #     packages:
    #       - python
    #       - tmux
    #     sources:
    #       - https://github.com/mshroyer/tsock
    #     tasks:
    #       - test: |
    #           cd tsock
    #           ./scripts/test.sh
    #     """)
    # )
    # print(f"build_id = {build_id}")

    # status = await client.get_job_status(1552562)
    # print(f"status = {status}")

    group = await manager.start_group_from_manifest_dir(
        "/home/mshroyer/code/tsock/scripts/srht_manifests"
    )
    jobs = group.jobs
    print(f"group: {group}")
    while True:
        print("")
        for job in jobs:
            print(f"job: {job}")

        if all(map(lambda j: j.status.is_terminal(), jobs)):
            break

        await asyncio.sleep(POLL_INTERVAL.seconds)
        jobs = await manager.update_job_statuses(jobs)


if __name__ == "__main__":
    asyncio.run(main())
