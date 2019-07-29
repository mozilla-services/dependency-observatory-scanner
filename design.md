### Design Notes

`find-package-rugaru` runs a data pipeline composed of one or more
analysis steps that fetch or infer data about the repository, diff, or
container image under analysis and output results to the another
analysis step or a final result aggregator.

#### Goals

* the pipeline of analysis steps should be flexible and possible to
  limit to a specific org, repo, dependency, dependency file,
  language, specific step, or other attribute

* as much as possible failures should be isolated and only affect
  downstream jobs
  * errors should be caught (and wehere applicable retried w/ delay or
    rate limiting) where applicable (e.g. request timeouts or rate
    limits) retried

* final output should be limited (i.e. not including fields we aren't
  using since it will break storage schemas). If necessarily, we
  should be able to pull additional fields from intermediate results
  without too much trouble.

* individual analysis steps that download or run third party analysis
  tools and packages should be containerized to reduce risk to the
  host system

* individual analysis steps should include Python input and output
  types and as much as possible document any IO side effects

#### Execution framework

Workload is IO heavy and (for now) small data so Beam, Spark, etc. and
other Big Data tools not directly applicable, but might make sense
later. So we're trying RxPy since it gives access to combinators with
async support (without relying on a pure generator pipeline).

Features from proper datapipeline tools we do want include:

* being able to save, restore, retry, and replay from checkpoints
  (i.e. not have to run a full task graph again and be able to test
  against fixtures)

* performance data for individual steps (i.e. add row UUIDs, track
  timings)
