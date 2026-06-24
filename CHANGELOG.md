# Changelog

All notable changes to this project will be tracked here.

## [0.1.1] - 2026-06-24

This release adds run-scoped output handling for the example pipeline and aligns runtime timestamps with local time.

### Added

- Introduced per-run output directories so each pipeline execution writes into its own `runs/<run_id>/` tree.
- Anchored the example pipeline to its own `main.py` directory so runs stay inside `examples/pipeline_1/` instead of the repository working directory.
- Routed stage output paths through `ExecutionContext.run_dir` so stages can record artifacts in the active run directory.
- Switched runtime timestamp generation to local time and kept a compatibility alias for the previous helper.
- Added regression coverage for repeated runs and run-specific output paths.


## [0.1.0] - 2026-06-22

First tracked version of `onsrap`.

This release establishes the initial package structure, the core pipeline orchestration model, the example pipeline deployment, and the first round of project documentation and tests.

### Added

- Core orchestration pieces for building and running simple pipelines.
- A realistic example pipeline under `examples/pipeline_1/`.
- Architecture and implementation notes to explain how the package fits together.
- Initial test coverage for the main package behavior.

