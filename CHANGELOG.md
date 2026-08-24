# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-08-24

### Added
- Merging Configuration implementation into Development to create a baseline functional point for an alpha release by @pikes-ons in [#66](https://github.com/ONSdigital/onsrap/pull/66)
- Added __str__ and __repr__ methods for key classes. by @BelowBayesline in [#39](https://github.com/ONSdigital/onsrap/pull/39)

### Changed
- Feat/ Adjust github action to remove recursion from CHANGELOG generation by @pikes-ons in [#83](https://github.com/ONSdigital/onsrap/pull/83)
- Test/all runs attribute by @pikes-ons in [#75](https://github.com/ONSdigital/onsrap/pull/75)
- Introduce Run-based Output Location Functionality by @BelowBayesline in [#5](https://github.com/ONSdigital/onsrap/pull/5)
- Merge branch 'feat/run_history' into feat/config by @BelowBayesline
- Merge branch 'feat/config' into feat/run_history by @pikes-ons
- Merge branch 'feat/config' into feat/refactor by @BelowBayesline
- Adds capability for configuration logging at runtime for each Pipeline run. by @pikes-ons in [#60](https://github.com/ONSdigital/onsrap/pull/60)
- Implemented fix/stage_logic branch into test_warning_resolutions ahead of implementation with gloabl_config branch in feat/config to consolidate branches. by @BelowBayesline in [#54](https://github.com/ONSdigital/onsrap/pull/54)
- Pipeline handling by @BelowBayesline in [#36](https://github.com/ONSdigital/onsrap/pull/36)
- Resolve todos merge into pipeline_handling - handled a lot of PipelineConfig management but still need to resolve certain stages_to_run logic in Pipeline & PipelineConfig and how that interacts with StageGraph during development. by @BelowBayesline in [#31](https://github.com/ONSdigital/onsrap/pull/31)
- Merge branch 'example_2' into pipeline_handling by @BelowBayesline
- Multiple bug fixes by @pikes-ons in [#21](https://github.com/ONSdigital/onsrap/pull/21)
- Finished documenting the modules by @BelowBayesline in [#11](https://github.com/ONSdigital/onsrap/pull/11)
- Adding docstrings to stage.py, errors.py, and execution.py by @pikes-ons in [#7](https://github.com/ONSdigital/onsrap/pull/7)

### Fixed
- Fix/add action sha by @pikes-ons in [#80](https://github.com/ONSdigital/onsrap/pull/80)
- Fix/testing checkpoint by @pikes-ons in [#64](https://github.com/ONSdigital/onsrap/pull/64)
- Fix/generate execution context, add methodology to assign execution context based on other given parameters by @pikes-ons in [#63](https://github.com/ONSdigital/onsrap/pull/63)
- Merges fix/output_locations into feat/config. Provides functionality that ensures that overwriting, whilst possible, is warned. by @pikes-ons in [#62](https://github.com/ONSdigital/onsrap/pull/62)
- Fix: added "global_variables" and "global_vars" as options for keys i…
CoPilot reviewed and only minor comments identified so merge going ahead. by @pikes-ons in [#58](https://github.com/ONSdigital/onsrap/pull/58)

### New Contributors
* @pikes-ons made their first contribution
* @github-actions[bot] made their first contribution

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
