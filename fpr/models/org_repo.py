from dataclasses import dataclass, field
from typing import Dict, Tuple, Sequence


@dataclass
class OrgRepo:
    org: str
    repo: str
    languages: list = field(default_factory=list)
    dep_files: list = field(default_factory=list)
    dep_file_deps: dict = field(default_factory=dict)

    # map of manifest/dep_file_id to the query params (end cursor and page
    # size) to fetch it (since GH's GQL API doesn't let us query by node id
    # yet)
    dep_file_query_params: dict = field(default_factory=dict)

    @property
    def github_clone_url(self) -> str:
        return "https://github.com/{0.org}/{0.repo}.git".format(self)

    def iter_dep_files(self) -> Dict:
        for df in self.dep_files:
            if df and df.node:
                yield self, df.node

    def iter_dep_file_deps(self) -> Tuple[Dict, Dict]:
        for _, df in self.iter_dep_files():
            if df.id not in self.dep_file_deps:
                continue

            for dep in self.dep_file_deps[df.id]:
                yield self, df, dep

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
