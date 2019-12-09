from dataclasses import dataclass, field
from typing import Any, Dict, Tuple, Sequence, Generator, Optional, List


@dataclass
class OrgRepo:
    org: str
    repo: str

    @property
    def github_clone_url(self) -> str:
        return "https://github.com/{0.org}/{0.repo}.git".format(self)

    @staticmethod
    def from_org_repo(org_repo):
        """e.g. mozilla/gecko-dev -> OrgRepo(org=mozilla, repo=gecko-dev)"""
        return OrgRepo(*org_repo.split("/", 1))

    @staticmethod
    def from_github_repo_url(repo_url):
        """e.g. https://github.com/mozilla-services/syncstorage-rs.git
        -> OrgRepo(org=mozilla-services, repo=syncstorage-rs)
        """
        org_repo = repo_url.replace("https://github.com/", "").replace(".git", "")
        return OrgRepo.from_org_repo(org_repo)
