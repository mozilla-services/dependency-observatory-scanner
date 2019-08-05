## find-package-rugaru

`find-package-rugaru` finds open source dependent packages in a git
repository and tests and flags suspicious open source packages (like
[the legendary rugaru](https://en.wikipedia.org/wiki/Rougarou)).

*NB: this project is in any alpha state*

### Example Usage

```console
$ cat tests/fixtures/mozilla_services_channelserver.csv

repo_url
https://github.com/mozilla-services/channelserver
$ PYTHONPATH=$PYTHONPATH:fpr/ python fpr/run_pipeline.py cargo_metadata tests/fixtures/mozilla_services_channelserver.csv
```
