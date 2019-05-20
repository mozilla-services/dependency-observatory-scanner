import enum


@enum.unique
class ResponseType(enum.Enum):
    REPOSITORY = enum.auto()


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

    # assume there aren't too enough of items in array fields to exceed
    # BigQuery's 100MB row size limit
    row["languages"] = list(serialize_repo_langs_iter(repo))
    row["languages_count"] = len(row["languages"])
    row["languages_bytes"] = repo.languages.totalSize

    row["dependencyGraphManifests"] = list(serialize_repo_manifests_iter(repo))
    row["dependencyGraphManifests_count"] = len(row["dependencyGraphManifests"])

    row["dependencies"] = list(serialize_repo_manifest_deps_iter(repo))
    row["dependencies_count"] = len(row["dependencies"])

    row["vulnerabilityAlerts"] = list(serialize_repo_vuln_alerts_iter(repo))
    row["vulnerabilityAlerts_count"] = len(row["vulnerabilityAlerts"])

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
    row["securityAdvisory"] = serialize_advisory(edge.node.securityAdvisory)
    row.update(serialize_vuln_alert_dismissal(edge.node))
    return row


def serialize_advisory(advisory):
    row = {
        field: getattr(advisory, field, Sentinal)
        for field in dir(advisory)
        if not field.startswith("__")
        and type(getattr(advisory, field, Sentinal)) in SCALAR_TYPES
    }
    row["severity"] = advisory.severity.value  # .value since it's an enum
    row["identifiers"] = [
        {"type": sa_id.type, "value": sa_id.value} for sa_id in advisory.identifiers
    ]
    row["vulnerabilities"] = [
        n for n in serialize_vulns_iter(advisory.vulnerabilities.nodes)
    ]
    row["referenceUrls"] = [
        getattr(r, "url", None) for r in getattr(advisory, "references", [])
    ]
    return row


def serialize_vulns_iter(vulns):
    for vuln in vulns:
        first_patched_version = getattr(vuln, "firstPatchedVersion", None)
        package = getattr(vuln, "package", None)

        row = {
            "firstPatchedVersion": {
                "identifier": first_patched_version
                and getattr(first_patched_version, "identifier", None)
            },
            "package": {
                "ecosystem": package
                and getattr(package, "ecosystem", None)
                and package.ecosystem.value,
                "name": package and getattr(package, "name", None),
            },
            "severity": getattr(vuln, "severity", None) and vuln.severity.value,
            "updatedAt": getattr(vuln, "updatedAt", None),
            "vulnerableVersionRange": getattr(vuln, "vulnerableVersionRange", None),
        }
        yield row


def serialize_vuln_alert_dismissal(vuln_alert):
    row = {}
    for field in ["dismissedAt", "dismissReason"]:
        row[field] = getattr(vuln_alert, field, None)

    dismisser = getattr(vuln_alert, "dismisser", None)
    row["dismisser"] = {
        getattr(dismisser, field, None) for field in ["id", "name"] if dismisser
    }
    return row


def serialize_result(repo):
    """
    Generator yielding (ResponseType, serialized dict) for an
    org-repo and its constituent items.
    """
    yield ResponseType.REPOSITORY, serialize_repo(repo)
