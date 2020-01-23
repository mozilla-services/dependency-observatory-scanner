from fpr.pipelines.cargo_audit import pipeline as cargo_audit
from fpr.pipelines.cargo_metadata import pipeline as cargo_metadata
from fpr.pipelines.crate_graph import pipeline as crate_graph
from fpr.pipelines.dep_graph import pipeline as dep_graph
from fpr.pipelines.fetch_package_data import pipeline as fetch_package_data
from fpr.pipelines.find_git_refs import pipeline as find_git_refs
from fpr.pipelines.find_dep_files import pipeline as find_dep_files
from fpr.pipelines.rust_changelog import pipeline as rust_changelog
from fpr.pipelines.github_metadata import pipeline as github_metadata
from fpr.pipelines.run_repo_tasks import pipeline as run_repo_tasks
from fpr.pipelines.postprocess import pipeline as postprocess

pipelines = [
    cargo_audit,
    cargo_metadata,
    crate_graph,
    dep_graph,
    fetch_package_data,
    find_git_refs,
    find_dep_files,
    github_metadata,
    rust_changelog,
    run_repo_tasks,
    postprocess,
]
