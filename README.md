## find-package-rugaru

`find-package-rugaru` finds open source dependent packages in a git
repository and tests and flags suspicious open source packages (like
[the legendary rugaru](https://en.wikipedia.org/wiki/Rougarou)).

*NB: this project is in an alpha state*

### Example Usage

```console
$ docker pull gguthemoz/fpr
$ echo '{"repo_url": "https://github.com/mozilla-services/channelserver"}' | docker run -i --rm -v /var/run/docker.sock:/var/run/docker.sock --name fpr-test gguthemoz/fpr python fpr/run_pipeline.py -v find_git_refs
```

### Local Development

```console
$ git clone https://github.com/mozilla-services/find-package-rugaru.git
$ cd find-package-rugaru
$ pipenv install --python 3.7.4
$ cat tests/fixtures/mozilla_services_channelserver_branch.jsonl
{"repo_url": "https://github.com/mozilla-services/channelserver", "ref": {"value": "master", "kind": "branch"}}
$ PYTHONPATH=$PYTHONPATH:fpr/ pipenv run python fpr/run_pipeline.py cargo_metadata -i tests/fixtures/mozilla_services_channelserver.csv --outfile=output.jsonl
2019-08-06 16:23:20,159 - fpr - INFO - running pipeline cargo_metadata on tests/fixtures/mozilla_services_channelserver.csv writing to output.jsonl
2019-08-06 16:23:20,162 - fpr.pipelines.cargo_metadata - INFO - pipeline started
2019-08-06 16:23:20,163 - fpr.containers - INFO - building image dep-obs/cargo-metadata
2019-08-06 16:23:20,686 - fpr.containers - INFO - built docker image: dep-obs/cargo-metadata sha256:4c38f1977ba105f2332f7e1bc030835a98941bd534702975317c804137ac2898
2019-08-06 16:23:20,687 - fpr.pipelines.cargo_metadata - INFO - tagged image dep-obs/cargo-metadata
2019-08-06 16:23:20,687 - fpr.pipelines.cargo_metadata - INFO - image built successfully
2019-08-06 16:23:20,690 - fpr.containers - INFO - starting image dep-obs/cargo-metadata:latest as dep-obs-cargo-metadata-mozilla-services-channelserver
...
2019-08-06 16:23:57,965 - fpr.containers - INFO - container /dep-obs-cargo-metadata-mozilla-services-channelserver in /repo ran {'Cmd': ['cargo', 'metadata', '--format-version', '1', '--locked'], 'AttachStdout': True, 'AttachStderr': True, 'WorkingDir': '/repo'} saved start result to /tmp/fpr_container_b7abcbbf44dde1a0aff8b1994f83de41009de2721324ff60bcb40feab65f2d93_exec_cef3dd0985b9b13f3b54af18f80221069ec17cc54cb88b76af74053dae2689f2_stdoutqmi7dv6x
2019-08-06 16:24:00,080 - fpr - INFO - pipeline finished
$ jq '' output.jsonl | head -25
{
  "repo": "channelserver",
  "org": "mozilla-services",
  "rustc_version": "rustc 1.36.0 (a53f9df32 2019-07-03)",
  "cargo_tomlfile_path": "Cargo.toml",
  "ripgrep_version": "ripgrep 11.0.1 (rev 1f1cd9b467)",
  "cargo_version": "cargo 1.36.0 (c4fcfb725 2019-05-15)",
  "commit": "79157df7b193857a2e7e3fe8e61e38305e1d47d4",
  "metadata": {
    "version": 1,
    "root": null,
    "nodes": [
      {
        "id": "MacTypes-sys 2.1.0 (registry+https://github.com/rust-lang/crates.io-index)",
        "deps": [
          {
            "name": "libc",
            "pkg": "libc 0.2.51 (registry+https://github.com/rust-lang/crates.io-index)"
          }
        ],
        "features": [
          "default",
          "libc",
          "use_std"
        ]
```
