import enum


@enum.unique
class ResponseType(enum.Enum):
    REPOSITORY = enum.auto()
    LANGUAGE = enum.auto()
    DEPENDENCY_MANIFEST = enum.auto()
    DEPENDENCY = enum.auto()
    VULNERABILITY_ALERT = enum.auto()


class Sentinal:
    "A Sentinal type so we to distinguish from fields with value None. type of this is type"
    pass


SCALAR_TYPES = {str, bool, int, float, type(None)}


def serialize_repo(repo):
    # 'createdAt', 'description', 'isArchived', 'isFork', 'isPrivate', 'updatedAt'
    row = {
        f: getattr(repo, f)
        for f in dir(repo)
        if not f.startswith("__") and type(getattr(repo, f, Sentinal)) in SCALAR_TYPES
    }
    row["languages.totalCount"] = repo.languages.totalCount
    row["languages.totalSize"] = repo.languages.totalSize  # in bytes
    row[
        "dependencyGraphManifests.totalCount"
    ] = repo.dependencyGraphManifests.totalCount
    row["vulnerabilityAlerts.totalCount"] = repo.vulnerabilityAlerts.totalCount
    return row


def serialize_repo_langs_iter(repo):
    for edge in repo.languages.edges:
        row = {
            field: getattr(edge.node, field, Sentinal) for field in set(["id", "name"])
        }
        yield row


def serialize_repo_manifests_iter(repo):
    for edge in repo.dependencyGraphManifests.edges:
        # blobPath,dependenciesCount,exceedsMaxSize,filename,id,org,parseable,repo
        row = {
            field: getattr(edge.node, field, Sentinal)
            for field in dir(edge.node)
            if not field.startswith("__")
            and type(getattr(edge.node, field, Sentinal)) in SCALAR_TYPES
        }
        yield row


def serialize_repo_manifest_deps_iter(repo):
    for _tmp in repo.dependencyGraphManifests.edges:
        manifest_edge = _tmp.node
        for dep in manifest_edge.dependencies.nodes:
            row = {
                field: getattr(dep, field, Sentinal)
                for field in dir(dep)
                if not field.startswith("__")
                and type(getattr(dep, field, Sentinal)) in SCALAR_TYPES
            }
            row["manifest_filename"], row["manifest_id"] = (
                manifest_edge.filename,
                manifest_edge.id,
            )
            yield row


def serialize_repo_vuln_alerts_iter(repo):
    for edge in repo.vulnerabilityAlerts.edges:
        yield serialize_vuln_alert(edge)


def serialize_vuln_alert(edge):
    row = {
        field: getattr(edge.node, field, Sentinal)
        for field in dir(edge.node)
        if not field.startswith("__")
        and type(getattr(edge.node, field, Sentinal)) in SCALAR_TYPES
    }
    row.update(serialize_advisory(edge.node.securityAdvisory))
    row.update(serialize_vuln_alert_dismisser(edge.node))
    return row


def serialize_advisory(advisory):
    row = {
        "securityAdvisory." + field: getattr(advisory, field, Sentinal)
        for field in dir(advisory)
        if not field.startswith("__")
        and type(getattr(advisory, field, Sentinal)) in SCALAR_TYPES
    }
    row[
        "securityAdvisory.severity"
    ] = advisory.severity.value  # .value since it's an enum
    row["securityAdvisory.identifiers"] = [
        (sa_id.type, sa_id.value) for sa_id in advisory.identifiers
    ]
    row["securityAdvisory.vulnerabilities"] = [
        n for n in serialize_vulns_iter(advisory.vulnerabilities.nodes)
    ]
    row["securityAdvisory.referenceUrls"] = [
        getattr(r, "url", None) for r in getattr(advisory, "references", [])
    ]
    return row


def serialize_vulns_iter(vulns):
    for vuln in vulns:
        row = {
            "firstPatchedVersion.identifier": getattr(vuln, "firstPatchedVersion", None)
            and getattr(vuln.firstPatchedVersion, "identifier", None),
            "package.ecosystem": getattr(vuln, "package", None)
            and getattr(vuln.package, "ecosystem", None)
            and vuln.package.ecosystem.value,
            "package.name": getattr(vuln, "package", None)
            and getattr(vuln.package, "name", None),
            "severity": getattr(vuln, "severity", None) and vuln.severity.value,
            "updatedAt": getattr(vuln, "updatedAt", None),
            "vulnerableVersionRange": getattr(vuln, "vulnerableVersionRange", None),
        }
        yield row


def serialize_vuln_alert_dismisser(vuln_alert):
    dismisser = getattr(vuln_alert, "dismisser", None)

    row = {}
    for field in ["dismissedAt", "dismissReason"]:
        row[field] = getattr(vuln_alert, field, None)

    for field in ["dismisser.id", "dismisser.name"]:
        if dismisser:
            row[field] = getattr(dismisser, field.split(".", 1)[-1], None)
        else:
            row[field] = None
    return row


def serialize_result(repo):
    """
    Generator yielding (ResponseType, serialized dict) for an
    org-repo and its constituent items.
    """
    yield ResponseType.REPOSITORY, serialize_repo(repo)

    for row in serialize_repo_langs_iter(repo):
        yield ResponseType.LANGUAGE, row

    for row in serialize_repo_manifests_iter(repo):
        yield ResponseType.DEPENDENCY_MANIFEST, row

    for row in serialize_repo_manifest_deps_iter(repo):
        yield ResponseType.DEPENDENCY, row

    for row in serialize_repo_vuln_alerts_iter(repo):
        yield ResponseType.VULNERABILITY_ALERT, row
