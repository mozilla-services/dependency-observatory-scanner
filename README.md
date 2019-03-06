## find-package-rugaru

Scripts for finding suspicious werewolf / rugaru / rougarou-like malware open source packages.

### Usage

#### Requirements


### How does this differ from other tools?

* language agnostic
* sandboxed


### Directions

1. clone this repo (while in development we won't publish)

```console
git clone https://github.com/mozilla-services/find-package-rugaru.git

```

2. Inspect a container:

```console

```

3. Optionally, we can containerize a repo first from a base image to inspect:


```console

```

####

* base docker images names for testing repos (Python, JS, etc.). These should be official or trusted (in the "I wrote this or trust the authors not ) docker images

### Repo layout

* `./bin/` scripts to run other scripts
* `./container_bin/` scripts that get mounted in `/tmp/bin/`

#### Files

* `./bin/base_image_config.json`
* `./bin/base_image_config.json.lock` hashes



These scripts generally assume the containers follow [dockerflow](https://github.com/mozilla-services/Dockerflow) i.e.

* app source is in `/app`
* `/app/version.json` exists and includes repo, version, and CI build info
