import sys
import json

"""
Example usage:

jq '.dirs[].commands[].stdout | fromjson' mozilla_fxa-auth-server.package_info.json | flatten_npm_info.py

Takes a nested obj:

{
}

and outputs

STRUCT<`name`: STRING, `version`: STRING, `type`: STRING, `registryUrl`: STRING, `integrity`: STRING, `paths`: ARRAY<STRING>>
"""


def get_dep_path_id(dep, dep_key):
    return (
        dep.get("_from", None)
        or ("name" in dep and "version" in dep and "{0[name]}@{0[version]}".format(dep))
        or dep_key
    )


def get_dep(dep, path, dep_key):
    return dict(
        name=dep.get("name") or dep_key,
        version=dep.get("version"),
        url=dep.get("_resolved", None),
        integrity=dep.get("_integrity", None),
        path=path,
    )


{
  "name": "ajv",
  "version": "4.1.7",
  "description": "Another JSON Schema Validator",
  "author": {
    "name": "Evgeny Poberezkin"
  },
  "license": "MIT",
  "bugs": {
    "url": "https://github.com/epoberezkin/ajv/issues"
  },
  "dependencies": {
    "co": {
      "name": "co",
      "version": "4.6.0",
      "description": "generator async control flow goodness",
      "keywords": [
        "async",
        "flow",
        "generator",
        "coro",
        "coroutine"
      ],
      "devDependencies": {
        "browserify": "^10.0.0",
        "istanbul-harmony": "0",
        "mocha": "^2.0.0",
        "mz": "^1.0.2"
      },
      "scripts": {
        "test": "mocha --harmony",
        "test-cov": "node --harmony node_modules/.bin/istanbul cover ./node_modules/.bin/_mocha -- --reporter dot",
        "test-travis": "node --harmony node_modules/.bin/istanbul cover ./node_modules/.bin/_mocha --report lcovonly -- --reporter dot",
        "prepublish": "npm run browserify",
        "browserify": "browserify index.js -o ./co-browser.js -s co"
      },
      "files": [
        "index.js"
      ],
      "license": "MIT",
      "repository": {
        "type": "git",
        "url": "git+https://github.com/tj/co.git"
      },
      "engines": {
        "iojs": ">= 1.0.0",
        "node": ">= 0.12.0"
      },
      "_resolved": "https://registry.npmjs.org/co/-/co-4.6.0.tgz",
      "_integrity": "sha1-bqa989hTrlTMuOR7+gvz+QMfsYQ=",
      "_from": "co@4.6.0",
      "readme": "",
      "readmeFilename": "Readme.md",
      "bugs": {
        "url": "https://github.com/tj/co/issues"
      },
      "homepage": "https://github.com/tj/co#readme",
      "_id": "co@4.6.0",
      "_requested": {
        "type": "version",
        "registry": True,
        "raw": "co@4.6.0",
        "name": "co",
        "escapedName": "co",
        "rawSpec": "4.6.0",
        "saveSpec": None,
        "fetchSpec": "4.6.0"
      },
      "_spec": "4.6.0",
      "_where": "/app",
      "_args": [
        [
          "co@4.6.0",
          "/app"
        ]
      ],
      "dependencies": {},
      "optionalDependencies": {},
      "_dependencies": {},
      "path": "/app/node_modules/co",
      "error": "[Circular]",
      "extraneous": False
    },
    "json-stable-stringify": {
      "name": "json-stable-stringify",
      "version": "1.0.1",
      "description": "deterministic JSON.stringify() with custom sorting to get deterministic hashes from stringified results",
      "main": "index.js",
      "dependencies": {
        "jsonify": {
          "name": "jsonify",
          "version": "0.0.0",
          "description": "JSON without touching any globals",
          "main": "index.js",
          "directories": {
            "lib": ".",
            "test": "test"
          },
          "devDependencies": {
            "tap": "0.0.x",
            "garbage": "0.0.x"
          },
          "scripts": {
            "test": "tap test"
          },
          "repository": {
            "type": "git",
            "url": "git+ssh://git@github.com/substack/jsonify.git"
          },
          "keywords": [
            "json",
            "browser"
          ],
          "author": {
            "name": "Douglas Crockford",
            "url": "http://crockford.com/"
          },
          "license": "Public Domain",
          "_resolved": "https://registry.npmjs.org/jsonify/-/jsonify-0.0.0.tgz",
          "_integrity": "sha1-LHS27kHZPKUbe1qu6PUDYx0lKnM=",
          "_from": "jsonify@0.0.0",
          "readme": "",
          "readmeFilename": "README.markdown",
          "bugs": {
            "url": "https://github.com/substack/jsonify/issues"
          },
          "homepage": "https://github.com/substack/jsonify#readme",
          "_id": "jsonify@0.0.0",
          "_requested": {
            "type": "version",
            "registry": True,
            "raw": "jsonify@0.0.0",
            "name": "jsonify",
            "escapedName": "jsonify",
            "rawSpec": "0.0.0",
            "saveSpec": "[Circular]",
            "fetchSpec": "0.0.0"
          },
          "_spec": "0.0.0",
          "_where": "/app",
          "_args": [
            [
              "jsonify@0.0.0",
              "/app"
            ]
          ],
          "dependencies": {},
          "optionalDependencies": {},
          "_dependencies": {},
          "path": "/app/node_modules/jsonify",
          "error": "[Circular]",
          "extraneous": False
        }
      },
      "devDependencies": {
        "tape": "~1.0.4"
      },
      "scripts": {
        "test": "tape test/*.js"
      },
      "testling": {
        "files": "test/*.js",
        "browsers": [
          "ie/8..latest",
          "ff/5",
          "ff/latest",
          "chrome/15",
          "chrome/latest",
          "safari/latest",
          "opera/latest"
        ]
      },
      "repository": {
        "type": "git",
        "url": "git://github.com/substack/json-stable-stringify.git"
      },
      "homepage": "https://github.com/substack/json-stable-stringify",
      "keywords": [
        "json",
        "stringify",
        "deterministic",
        "hash",
        "sort",
        "stable"
      ],
      "author": {
        "name": "James Halliday",
        "email": "mail@substack.net",
        "url": "http://substack.net"
      },
      "license": "MIT",
      "_resolved": "https://registry.npmjs.org/json-stable-stringify/-/json-stable-stringify-1.0.1.tgz",
      "_integrity": "sha1-mnWdOcXy/1A/1TAGRu1EX4jE+a8=",
      "_from": "json-stable-stringify@1.0.1",
      "readme": "",
      "readmeFilename": "readme.markdown",
      "bugs": {
        "url": "https://github.com/substack/json-stable-stringify/issues"
      },
      "_id": "json-stable-stringify@1.0.1",
      "_requested": {
        "type": "version",
        "registry": True,
        "raw": "json-stable-stringify@1.0.1",
        "name": "json-stable-stringify",
        "escapedName": "json-stable-stringify",
        "rawSpec": "1.0.1",
        "saveSpec": "[Circular]",
        "fetchSpec": "1.0.1"
      },
      "_spec": "1.0.1",
      "_where": "/app",
      "_args": [
        [
          "json-stable-stringify@1.0.1",
          "/app"
        ]
      ],
      "optionalDependencies": {},
      "_dependencies": {
        "jsonify": "~0.0.0"
      },
      "path": "/app/node_modules/json-stable-stringify",
      "error": "[Circular]",
      "extraneous": False
    }
  },
  "devDependencies": {
    "bluebird": "^3.1.5",
    "brfs": "^1.4.3",
    "browserify": "^13.0.0",
    "chai": "^3.5.0",
    "coveralls": "^2.11.4",
    "dot": "^1.0.3",
    "eslint": "^2.10.1",
    "gh-pages-generator": "^0.2.0",
    "glob": "^7.0.0",
    "istanbul": "^0.4.2",
    "js-beautify": "^1.5.6",
    "jshint": "^2.8.0",
    "json-schema-test": "^1.1.1",
    "karma": "^1.0.0",
    "karma-chrome-launcher": "^1.0.1",
    "karma-mocha": "^1.1.1",
    "karma-phantomjs-launcher": "^1.0.0",
    "karma-sauce-launcher": "^0.3.0",
    "mocha": "^2.5.0",
    "nodent": "^2.5.3",
    "phantomjs-prebuilt": "^2.1.4",
    "pre-commit": "^1.1.1",
    "regenerator": "0.8.42",
    "require-globify": "^1.3.0",
    "typescript": "^1.8.10",
    "uglify-js": "^2.6.1",
    "watch": "^0.19.1"
  },
  "_resolved": "https://registry.npmjs.org/ajv/-/ajv-4.1.7.tgz",
  "_integrity": "sha1-Gx5Yz3NWzoE1FsI57JKJSSRROpk=",
  "_from": "ajv@4.1.7",
  "readme": "",
  "readmeFilename": "README.md",
  "_id": "ajv@4.1.7",
  "_requested": {
    "type": "version",
    "registry": True,
    "raw": "ajv@4.1.7",
    "name": "ajv",
    "escapedName": "ajv",
    "rawSpec": "4.1.7",
    "saveSpec": "[Circular]",
    "fetchSpec": "4.1.7"
  },
  "_spec": "4.1.7",
  "_where": "/app",
  "_args": [
    [
      "ajv@4.1.7",
      "/app"
    ]
  ],
  "optionalDependencies": {},
  "_dependencies": {
    "co": "^4.6.0",
    "json-stable-stringify": "^1.0.1"
  },
  "path": "/app/node_modules/ajv",
  "error": "[Circular]",
  "extraneous": False
}


def list_deps(dep, dep_key=None, path=None, dep_arr=None):
    """
    Examples:

    >>> list_deps({})
    [{'name': None, 'version': None, 'url': None, 'integrity': None, 'path': []}]

    >>> list_deps({}) == list_deps({}, None, [], [])
    True

    >>> list_deps(dict(name='my_pkg', version='0.0'))
    [{'name': 'my_pkg', 'version': '0.0', 'url': None, 'integrity': None, 'path': []}]

    >>> list_deps(dict(name='my_pkg', version='0.0', dependencies=dict(ajv=dict(name="ajv",version="4.1.7")))) # doctest: +NORMALIZE_WHITESPACE
    [{'name': 'my_pkg', 'version': '0.0', 'url': None, 'integrity': None, 'path': []},
     {'name': 'ajv', 'version': '4.1.7', 'url': None, 'integrity': None, 'path': ['my_pkg@0.0']}]

    >>> for dep in list_deps(
    ...     dict(name='my_pkg',
    ...          version='0.0',
    ...          dependencies=dict(
    ...              ajv=dict(name="ajv",
    ...                       version="4.1.7",
    ...                       dependencies={"uap-core": {"version": "git://github.com/ua-parser/uap-core.git#add7bafbb3ba57256d1b919103add1b2cab97aa7", "from": "git://github.com/ua-parser/uap-core.git"}}
    ...              )
    ...          )
    ...     )
    ... ): print(dep) # doctest: +NORMALIZE_WHITESPACE
    {'name': 'my_pkg', 'version': '0.0', 'url': None, 'integrity': None, 'path': []}
    {'name': 'ajv', 'version': '4.1.7', 'url': None, 'integrity': None, 'path': ['my_pkg@0.0']}
    {'name': 'uap-core', 'version': 'git://github.com/ua-parser/uap-core.git#add7bafbb3ba57256d1b919103add1b2cab97aa7', 'url': None, 'integrity': None, 'path': ['my_pkg@0.0', 'ajv@4.1.7']}
    """
    if path is None:
        path = []
    if dep_arr is None:
        dep_arr = []

    dep_arr.append(get_dep(dep, path, dep_key))

    for child_dep_key, child_dep in dep.get("dependencies", {}).items():
        list_deps(child_dep, child_dep_key, path + [get_dep_path_id(dep, dep_key)], dep_arr)

    return dep_arr


def main():
    result = list_deps(json.load(sys.stdin))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
