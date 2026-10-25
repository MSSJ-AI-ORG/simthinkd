# Document register: SimThink D 0.4.0 (router kit)

Form: **agile, light**. Each document type of the six life-cycle stages has one line: the file that stands in for it,
or "not applicable" with the reason. "Internal" means it exists outside this repository and is not published.

## Requirements (SRS substitute)

| ID | Requirement |
|---|---|
| R1 | `Router` (new API): decide, then either a fast action or a hand-over with a reason: low confidence, no progress, unknown state. The no-progress check compares the observed next state with the expected next state after an action, and it is a core feature. |
| R2 | Expected next state per action (skill table), so that a confident wrong action is caught at once. |
| R3 | Relearning loop `relearn`: when the hand-over rate passes a threshold, collect teacher answers, retrain, hot-swap the model and log it. |
| R4 | Feature adapters: screen (pixel grid, window title), pipeline step (request meta, gate verdict), robot (part of an observation vector). The decider is the same; only the input changes. |
| R5 | A reproducibility test and a preregistration template (PREREG sealed by hash) as a repository example. |
| R6 | Backward compatibility: the 0.3.0 public API and its tests are unchanged. |
| R7 | DOM input as an extra or alternative input, and a two-step hybrid (capture decides, DOM verifies). No typed values leak, bounded length, deterministic order. The frozen router.py, relearn.py and adapters.py are not changed (CEO Telegram msg 8916, 8918). |

## Requirements traceability (RTM)

| Req | Design | Code | Tests | Result |
|---|---|---|---|---|
| R1 | docs/ROUTER.md (Parts, Rules 1-6) | src/simthinkd/router.py: `Router`, `Route`, reasons `low_confidence` / `unknown_state` / `no_progress` | tests/test_router.py: `test_low_confidence_hands_over`, `test_unknown_state_hands_over`, `test_no_progress_same_state_after_a_fast_action`, `test_no_progress_unexpected_state_catches_a_confident_wrong_action`, `test_reasons_are_checked_in_order`, `test_start_expectation_and_reset`, `test_handoff_clears_the_expectation_and_expect_sets_it`, `test_check_progress_has_no_side_effect`, `test_router_refusals`, `test_hot_swap_under_concurrent_routing` | pass |
| R2 | docs/ROUTER.md (Rules 2-4) | router.py: `Skill`, `SkillTable` (`from_transitions`, `expected_after`, `save` / `load`) | test_router.py: `test_deliberately_wrong_expected_state_is_caught` (negative), `test_skill_table_forms_and_equality`, `test_skill_table_save_and_load`, `test_skill_table_from_transitions`, `test_skill_refusals`, `test_final_skill_ends_the_checks`, `test_without_recorded_expectation_only_the_same_state_counts`; example negative controls (H3, H4) | pass |
| R3 | docs/ROUTER.md (Rule 7) | router.py: `HandoffMonitor`, `Router.take_handed_over`, `Router.swap`; src/simthinkd/relearn.py: `relearn`, `RelearnReport` | test_router.py: `test_monitor_*` (5), `test_relearn_*` (4), `test_handed_over_observations_are_kept_for_relearning`; tests/test_router_example.py (H5, H6, H7, swap + log line) | pass |
| R4 | docs/ROUTER.md (Adapters) | src/simthinkd/adapters.py: `ScreenAdapter`, `screen_tokens`, `PipelineAdapter`, `VectorAdapter` | test_router.py: `test_screen_tokens_match_the_v21_feature`, `test_screen_adapter_sentence`, `test_screen_adapter_refusals`, `test_pipeline_adapter_sentence`, `test_vector_adapter_sentence`, `test_same_router_different_inputs` | pass |
| R5 | examples/router_screen/README.md | examples/router_screen/: `run.py`, `screens.py`, `seal_prereg.py`, `PREREG_TEMPLATE.json`, `PREREG_router_screen.json` + `.sha256`, `RESULTS_router_screen_v1.json` | tests/test_router_example.py (seal verify, two runs with the same digest, H1-H7) | pass |
| R6 | CHANGELOG.md 0.4.0 | src/simthinkd/__init__.py (new names added, none removed) | test_router.py: `test_public_api_of_030_is_unchanged`, `test_router_on_a_real_decider_keeps_its_answers`, `test_router_loads_a_decider_by_name`; all 0.3.0 tests unchanged | pass |
| R7 | docs/ROUTER.md (DOM input) | src/simthinkd/dom_adapter.py: `DomAdapter`, `CombinedAdapter`, `DomVerifier`, `Verdict`, `VerifiedRouter`, `DOM_SNAPSHOT_JS`, reason `verify_disagree` | tests/test_dom_adapter.py: `test_dom_sentence_form`, `test_dom_order_is_deterministic`, `test_dom_length_is_bounded`, `test_no_typed_values_or_query_leak`, `test_combined_is_the_union`, `test_lookalike_told_apart_only_with_dom` (negative), `test_verifier_fit_and_reasons`, `test_verified_router_hands_over_on_disagreement`, `test_exports`; measured on the v2.1 test app in v28_dom_vs_capture_20261025 (internal) | pass |

## Register (35 document types)

| Stage | Document | Substitute or reason |
|---|---|---|
| 1 Plan | RFP | Internal: the status note that proposed 0.4.0 (section 4) and the approval of its scope |
| 1 Plan | Proposal / technical negotiation | Not applicable: internal product work, no client |
| 1 Plan | Project plan (PMP) | Internal status note (release order) + this register |
| 1 Plan | WBS | The RTM above (one row per requirement) |
| 1 Plan | Quality assurance plan | .github/workflows/test.yml + CONTRIBUTING.md + the test plan below |
| 1 Plan | Configuration management plan | git history, CHANGELOG.md, version in pyproject.toml and `__version__` |
| 1 Plan | Risk management plan | docs/ROUTER.md "Limits" |
| 2 Requirements | User requirements (URD) | Internal: the request that named the three uses (screen control, robot twin, pipeline routing) |
| 2 Requirements | Requirements specification (SRS) | "Requirements" above (R1-R6) |
| 2 Requirements | Traceability matrix (RTM) | "Requirements traceability" above |
| 2 Requirements | Use cases | README.md "Route between a fast path and a large model", examples/router_screen/README.md |
| 2 Requirements | Current / target process | Not applicable: a library, no business process |
| 3 Design | Architecture (SAD / ADR) | docs/ROUTER.md "Parts" and "Rules" (rule 3 records the decision to keep the v2.1 rule as the fallback) |
| 3 Design | Detailed design (SDD) | Module docstrings of router.py, relearn.py, adapters.py |
| 3 Design | Program list / specification | "Program list" below |
| 3 Design | ERD | Not applicable: no database |
| 3 Design | Table / column definitions | Not applicable: no database. File formats: `simthinkd-skills/1` (SkillTable.save) and `simthinkd-relearn/1` (relearn log), defined in router.py and relearn.py |
| 3 Design | Code definitions / standard dictionary | Hand-over reasons and details: docs/ROUTER.md; README.md "Words used here" |
| 3 Design | Interface (API) design | docs/ROUTER.md "Parts" table; docs/PROTOCOL.md (unchanged) |
| 3 Design | Screen design | Not applicable: no user interface added |
| 4 Build | Development standard | CONTRIBUTING.md; code style of the 0.3.0 modules |
| 4 Build | Development environment guide | README.md "Install"; `pip install -e ".[train]"` as in test.yml |
| 4 Build | Unit test results | Internal test log of this version (all suites); CI runs on every push |
| 5 Test | Test plan | "Test plan" below |
| 5 Test | Test case specification | tests/test_router.py, tests/test_router_example.py (each test name states its case) |
| 5 Test | Integration test results | tests/test_router_example.py output; examples/router_screen/RESULTS_router_screen_v1.json |
| 5 Test | System / performance / security test results | Performance: route ms in RESULTS_router_screen_v1.json (this machine only). Security: not applicable, because no network, files or secrets are added (relearn writes only to the `out` and `log` paths it is given) |
| 5 Test | Defect log | GitHub Issues. Found during this work: none open |
| 5 Test | User acceptance (UAT) | Pending: release approval |
| 6 Release | Data migration plan / result | Not applicable: no data format changed; 0.3.0 deciders load unchanged |
| 6 Release | Installation / release notes | CHANGELOG.md 0.4.0 |
| 6 Release | Operator manual | Not applicable: no service added (the HTTP server is unchanged) |
| 6 Release | User manual | README.md section, docs/ROUTER.md, examples/router_screen/README.md |
| 6 Release | Training plan / report | Not applicable |
| 6 Release | Project completion report | Internal completion report of this version |

## Program list

| File | Contents |
|---|---|
| src/simthinkd/router.py | `Skill`, `SkillTable`, `Route`, `HandoffMonitor`, `Router`, reason constants |
| src/simthinkd/relearn.py | `relearn`, `RelearnReport` |
| src/simthinkd/adapters.py | `color_class`, `screen_tokens`, `ScreenAdapter`, `PipelineAdapter`, `VectorAdapter` |
| src/simthinkd/dom_adapter.py | `DomAdapter`, `CombinedAdapter`, `DomVerifier`, `Verdict`, `VerifiedRouter`, `DOM_SNAPSHOT_JS` |
| src/simthinkd/__init__.py | exports, version 0.4.0 |
| examples/router_screen/screens.py | synthetic app (layouts A and B, disturbances) |
| examples/router_screen/run.py | example phases 1-7 |
| examples/router_screen/seal_prereg.py | seal and verify a PREREG |

## Test plan

- Every push: all 0.3.0 suites, then tests/test_router.py and tests/test_dom_adapter.py (NumPy only, under a second) and tests/test_router_example.py
  (needs PyTorch, about a minute).
- Every rule has a positive case and, where it can fail silently, a negative case (a planted wrong expectation, a
  planted wrong action, refusals that must leave the router unchanged).
- The example is preregistered. Its frozen code is checked by hash on every run of the test.

## Open items

- [ ] README.ko.md: translate the new section "Route between a fast path and a large model" (by a person, not by a machine), then `python tools/check_translations.py --stamp`.
- [ ] README.ja.md: the same.
- [ ] At release: CITATION.cff version and date, the version pill in web/index.html and web/i18n.js, the CHANGELOG date.
