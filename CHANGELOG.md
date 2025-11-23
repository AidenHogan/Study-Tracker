Summary of fixes and changes for GitHub upload

This file summarizes the code changes, bug fixes, and UX improvements implemented in the working tree before the GitHub upload.

High-level summary
- Fixed crashes and layout issues on Analytics tab (page 4 / Modeling).
- Offloaded heavy analytics computation to a background worker thread and rendered results on the main thread to prevent UI freezes.
- Added a simple loading overlay while background computations run.
- Implemented exploratory analyses (CCF, Event Study, Quantile) rendering reliably and fixed layout "smush" problems.
- Added data-confidence heuristic and automated short explanations for modeling/exploratory results.
- Fixed daily feature preparation:
  - Study days now start at the user's first recorded study session (missing earlier days are treated as inaccessible); days after the first session are filled with zero study minutes when appropriate.
- Improved `core.plot_manager` embedding logic to avoid collapsed Matplotlib layouts and to adapt figure size to container dimensions.
- Implemented tag archive vs full-delete workflow and added restore support (DB and UI), plus lightweight UI updates to reduce blocking during tag operations.
- Added pragmatic defensive programming around widget configure/destroy cycles to avoid invalid Tcl command errors.

Files touched (not exhaustive; main files):
- ui/analytics_tab.py
  - Background compute for modeling page, `_show_loading` overlay, layout weight fixes, deferred retry pass.
- core/correlation_engine.py
  - Routing fixes in `run_analysis()` for PLS / IRF / HMM / Weekly model types.
  - Added/verified: compute_ccf_heatmap_df, compute_event_study_df, run_quantile_regression, run_pls_analysis_full, run_var_irf, run_hmm_states, compute_data_confidence.
- core/plot_manager.py
  - Improved `embed_figure_in_frame()` to better size figures to hosting frame and schedule deferred redraws.
- core/database_manager.py
  - Added tag archive/restore functions; delete_tag updated to remove sessions for full delete.
- ui/ui_components.py
  - Tag management UI updated to ask Archive vs Full Delete and to restore archived tags.
- known_errors.txt
  - Removed issues that were fixed; kept remaining enhancement notes.

Testing/validation performed
- Ran the app to confirm no immediate crashes after edits.
- Exercised analytics page navigation, model dropdowns, and exploratory controls to validate layout stability and responsiveness.
- Verified tag archive/restore flows and that tag deletion no longer triggers long synchronous full refreshes.

Notes and guidance for reviewers
- Numerical warnings from numpy/statsmodels (divide-by-zero, quantile iteration limits) may appear in the console for small or poorly conditioned datasets; these are numerical issues and the engine returns friendly error payloads for many insufficient-data cases (e.g., "Not enough data for VAR/IRF"). Consider increasing sample thresholds or surfacing a clearer UI message if you want to suppress raw library warnings.
- Background workers currently ignore stale results by token; if you want to cancel running computations (cooperative cancellation), we should add cancellation-aware logic into the heavy compute functions (would require small API changes there).