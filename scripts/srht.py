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
from pathlib import Path
from typing import List, TypeVar
import os
import sys
import time

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport


ENDPOINT = "https://builds.sr.ht/query"

POLL_INTERVAL = timedelta(seconds=10)


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
    nickname: str
    canonical_name: str
    status: JobStatus

    def url(self) -> str:
        """Returns the URL of the build's status page"""
        return f"https://builds.sr.ht/{self.canonical_name}/job/{self.job_id}"


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
        manifest_file: Path,
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
            "manifest": manifest_file.read_text(),
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
            nickname=manifest_file.with_suffix("").name,
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
    _jobs: List[Job]
    _start_time: float

    def __init__(self, client: SourceHutClient, max_concurrency: int = 3):
        self._client = client
        self._max_concurrency = max_concurrency

    async def start_group_from_manifest_dir(self, manifest_dir: Path | str):
        """Starts a job group from YAML manifest files in a directory

        Returns the ID of the running group.

        """

        manifest_dir = Path(os.fspath(manifest_dir))
        manifests = list(manifest_dir.glob("*.yml"))

        self._jobs = await _run_with_bounded_concurrency(
            self._max_concurrency,
            self._start_manifest,
            manifests,
        )
        await self._client.create_group(self._jobs, note="")
        self._start_time = time.time()

    def print_job_links(self, include_statuses: bool):
        def get_status(job: Job):
            if include_statuses:
                return f"{str(job.status)}  "
            else:
                return ""

        for job in self._jobs:
            print(f"{job.nickname:<12} {get_status(job)}{job.url()}")

    def print_status_header(self):
        self._print_status_line_fn(lambda j: j.nickname)(self._jobs)
        self._print_status_line_fn(lambda j: "-" * (self._job_column_width(j)))(
            self._jobs
        )

    def print_status_line(self):
        self._print_status_line_fn(lambda j: str(j.status))(self._jobs)

    def _print_status_line_fn(
        self, fn: Callable[[Job], str]
    ) -> Callable[[List[Job]], None]:
        def result(jobs: List[Job]):
            print(f"| {int(time.time() - self._start_time):>3}s | ", end="")
            for job in jobs:
                print(f"{fn(job):<{self._job_column_width(job)}}", end="")
                print(" |", end="")
            print("")

        return result

    @staticmethod
    def _job_column_width(job: Job) -> int:
        return max(len(job.nickname), 9)

    def are_jobs_terminated(self) -> bool:
        return all(map(lambda j: j.status.is_terminal(), self._jobs))

    def are_jobs_successful(self) -> bool:
        return all(map(lambda j: j.status == JobStatus.SUCCESS, self._jobs))

    async def _start_manifest(self, manifest_file: Path) -> Job:
        name = manifest_file.with_suffix("").name
        return await self._client.submit_job(
            manifest_file,
            note=f"tsock.sh tests for {name}",
            tags=["tsock", name],
            execute=False,
        )

    async def refresh_job_statuses(self):
        """Get a list of jobs with updated statuses

        Returns a new list of Jobs with updated status fields.

        """

        self._jobs = await _run_with_bounded_concurrency(
            self._max_concurrency, self._get_updated_job, self._jobs
        )

    async def _get_updated_job(self, job: Job) -> Job:
        if job.status.is_terminal():
            return job

        new_status = await self._client.get_job_status(job.job_id)
        return Job(job.job_id, job.nickname, job.canonical_name, new_status)


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

    await manager.start_group_from_manifest_dir(
        "/home/mshroyer/code/tsock/scripts/srht_manifests"
    )

    print("Started jobs:\n")
    manager.print_job_links(False)
    print("\nCurrent statuses:\n")
    manager.print_status_header()
    while True:
        manager.print_status_line()
        if manager.are_jobs_terminated():
            break

        await asyncio.sleep(POLL_INTERVAL.seconds)
        await manager.refresh_job_statuses()

    print("")
    manager.print_job_links(True)

    if not manager.are_jobs_successful():
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
