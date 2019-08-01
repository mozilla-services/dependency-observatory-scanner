# -*- coding: utf-8 -*-

import pytest

import context
import fpr.pipelines.cargo_audit as m


@pytest.fixture
def cargo_audit_run_output():
    # TODO: read audit output from fixture file
    audit_output = '{"database":{"advisory-count":33},"lockfile":{"dependency-count":250,"path":"Cargo.lock"},"vulnerabilities":{"count":3,"found":true,"list":[{"advisory":{"affected_arch":null,"affected_os":null,"affected_paths":null,"aliases":[],"date":"2019-07-16","description":"Affected versions of this crate caused traps and/or memory unsafety by zero-initializing references.\\nThey also could lead to uninitialized memory being dropped if the field for which the offset is requested was behind a deref coercion, and that deref coercion caused a panic.\\n\\nThe flaw was corrected by using `MaybeUninit`.\\n","id":"RUSTSEC-2019-0011","keywords":[],"package":"memoffset","patched_versions":[">= 0.5.0"],"references":[],"title":"Flaw in offset_of and span_of causes SIGILL, drops uninitialized memory of arbitrary type on panic in client code","unaffected_versions":[],"url":"https://github.com/Gilnaa/memoffset/issues/9#issuecomment-505461490"},"package":{"dependencies":null,"name":"memoffset","source":"registry+https://github.com/rust-lang/crates.io-index","version":"0.2.1"}},{"advisory":{"affected_arch":null,"affected_os":null,"affected_paths":null,"aliases":[],"date":"2019-06-06","description":"Attempting to call `grow` on a spilled SmallVec with a value equal to the current capacity causes it to free the existing data. This performs a double free immediately and may lead to use-after-free on subsequent accesses to the SmallVec contents.\\n\\nAn attacker that controls the value passed to `grow` may exploit this flaw to obtain memory contents or gain remote code execution.\\n\\nCredits to @ehuss for discovering, reporting and fixing the bug.\\n","id":"RUSTSEC-2019-0009","keywords":["double free","use after free","arbitrary code execution"],"package":"smallvec","patched_versions":[">= 0.6.10"],"references":[],"title":"Double-free and use-after-free in SmallVec::grow()","unaffected_versions":["< 0.6.5"],"url":"https://github.com/servo/rust-smallvec/issues/148"},"package":{"dependencies":null,"name":"smallvec","source":"registry+https://github.com/rust-lang/crates.io-index","version":"0.6.9"}},{"advisory":{"affected_arch":null,"affected_os":null,"affected_paths":null,"aliases":[],"date":"2019-07-19","description":"Attempting to call `grow` on a spilled SmallVec with a value less than the current capacity causescorruption of memory allocator data structures.\\n\\nAn attacker that controls the value passed to `grow` may exploit this flaw to obtain memory contents or gain remote code execution.\\n\\nCredits to @ehuss for discovering, reporting and fixing the bug.\\n","id":"RUSTSEC-2019-0012","keywords":["memory corruption","arbitrary code execution"],"package":"smallvec","patched_versions":[">= 0.6.10"],"references":[],"title":"Memory corruption in SmallVec::grow()","unaffected_versions":["< 0.6.3"],"url":"https://github.com/servo/rust-smallvec/issues/149"},"package":{"dependencies":null,"name":"smallvec","source":"registry+https://github.com/rust-lang/crates.io-index","version":"0.6.9"}}]}}'  # noqa
    return {
        "org": "mozilla-services",
        "repo": "channelserver",
        "commit": "79157df7b193857a2e7e3fe8e61e38305e1d47d4",
        "cargo_version": "cargo 1.36.0 (c4fcfb725 2019-05-15)",
        "ripgrep_version": "ripgrep 11.0.1 (rev 1f1cd9b467)",
        "rustc_version": "rustc 1.36.0 (a53f9df32 2019-07-03)",
        "cargo_audit_version": "cargo-audit 0.7.0",
        "audit_output": audit_output,
    }


def test_serialize_returns_audit_result(cargo_audit_run_output):
    assert m.serialize(cargo_audit_run_output) == {
        "audit": {
            "lockfile_dependency_count": 250,
            "lockfile_path": "Cargo.lock",
            "vulnerabilities": [
                {
                    "advisory": {
                        "affected_arch": None,
                        "affected_os": None,
                        "affected_paths": None,
                        "aliases": [],
                        "date": "2019-07-16",
                        "description": "Affected versions "
                        "of this crate "
                        "caused traps "
                        "and/or memory "
                        "unsafety by "
                        "zero-initializing "
                        "references.\n"
                        "They also could "
                        "lead to "
                        "uninitialized "
                        "memory being "
                        "dropped if the "
                        "field for which "
                        "the offset is "
                        "requested was "
                        "behind a deref "
                        "coercion, and "
                        "that deref "
                        "coercion caused a "
                        "panic.\n"
                        "\n"
                        "The flaw was "
                        "corrected by "
                        "using "
                        "`MaybeUninit`.\n",
                        "id": "RUSTSEC-2019-0011",
                        "keywords": [],
                        "package": "memoffset",
                        "patched_versions": [">= 0.5.0"],
                        "references": [],
                        "title": "Flaw in offset_of and "
                        "span_of causes SIGILL, "
                        "drops uninitialized "
                        "memory of arbitrary "
                        "type on panic in client "
                        "code",
                        "unaffected_versions": [],
                        "url": "https://github.com/Gilnaa/memoffset/issues/9#issuecomment-505461490",
                    },
                    "package": {
                        "dependencies": None,
                        "name": "memoffset",
                        "source": "registry+https://github.com/rust-lang/crates.io-index",
                        "version": "0.2.1",
                    },
                },
                {
                    "advisory": {
                        "affected_arch": None,
                        "affected_os": None,
                        "affected_paths": None,
                        "aliases": [],
                        "date": "2019-06-06",
                        "description": "Attempting to "
                        "call `grow` on a "
                        "spilled SmallVec "
                        "with a value "
                        "equal to the "
                        "current capacity "
                        "causes it to free "
                        "the existing "
                        "data. This "
                        "performs a double "
                        "free immediately "
                        "and may lead to "
                        "use-after-free on "
                        "subsequent "
                        "accesses to the "
                        "SmallVec "
                        "contents.\n"
                        "\n"
                        "An attacker that "
                        "controls the "
                        "value passed to "
                        "`grow` may "
                        "exploit this flaw "
                        "to obtain memory "
                        "contents or gain "
                        "remote code "
                        "execution.\n"
                        "\n"
                        "Credits to @ehuss "
                        "for discovering, "
                        "reporting and "
                        "fixing the bug.\n",
                        "id": "RUSTSEC-2019-0009",
                        "keywords": [
                            "double free",
                            "use after free",
                            "arbitrary code " "execution",
                        ],
                        "package": "smallvec",
                        "patched_versions": [">= 0.6.10"],
                        "references": [],
                        "title": "Double-free and "
                        "use-after-free in "
                        "SmallVec::grow()",
                        "unaffected_versions": ["< 0.6.5"],
                        "url": "https://github.com/servo/rust-smallvec/issues/148",
                    },
                    "package": {
                        "dependencies": None,
                        "name": "smallvec",
                        "source": "registry+https://github.com/rust-lang/crates.io-index",
                        "version": "0.6.9",
                    },
                },
                {
                    "advisory": {
                        "affected_arch": None,
                        "affected_os": None,
                        "affected_paths": None,
                        "aliases": [],
                        "date": "2019-07-19",
                        "description": "Attempting to "
                        "call `grow` on a "
                        "spilled SmallVec "
                        "with a value less "
                        "than the current "
                        "capacity "
                        "causescorruption "
                        "of memory "
                        "allocator data "
                        "structures.\n"
                        "\n"
                        "An attacker that "
                        "controls the "
                        "value passed to "
                        "`grow` may "
                        "exploit this flaw "
                        "to obtain memory "
                        "contents or gain "
                        "remote code "
                        "execution.\n"
                        "\n"
                        "Credits to @ehuss "
                        "for discovering, "
                        "reporting and "
                        "fixing the bug.\n",
                        "id": "RUSTSEC-2019-0012",
                        "keywords": [
                            "memory corruption",
                            "arbitrary code " "execution",
                        ],
                        "package": "smallvec",
                        "patched_versions": [">= 0.6.10"],
                        "references": [],
                        "title": "Memory corruption in " "SmallVec::grow()",
                        "unaffected_versions": ["< 0.6.3"],
                        "url": "https://github.com/servo/rust-smallvec/issues/149",
                    },
                    "package": {
                        "dependencies": None,
                        "name": "smallvec",
                        "source": "registry+https://github.com/rust-lang/crates.io-index",
                        "version": "0.6.9",
                    },
                },
            ],
            "vulnerabilities_count": 3,
            "vulnerabilities_found": True,
        },
        "cargo_audit_version": "cargo-audit 0.7.0",
        "cargo_version": "cargo 1.36.0 (c4fcfb725 2019-05-15)",
        "commit": "79157df7b193857a2e7e3fe8e61e38305e1d47d4",
        "org": "mozilla-services",
        "repo": "channelserver",
        "ripgrep_version": "ripgrep 11.0.1 (rev 1f1cd9b467)",
        "rustc_version": "rustc 1.36.0 (a53f9df32 2019-07-03)",
    }
