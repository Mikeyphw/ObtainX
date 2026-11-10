# R00 Baseline Test Audit — NOT QUALIFIED

This inventory reflects the source code before R00 changes. The bootstrap has not executed Flutter, Gradle, or Android runtime tests.

- Upstream source commit: `aea18592413de992e813bd063cb9ad453259582b`
- Existing Dart test files: **69**
- Existing upstream golden-test failures have been reported; do not skip or relabel them as passing.

## Known missing qualification for future roadmap phases

| Area | Initial disposition |
|---|---|
| GitHub Actions artifact selection and workflow filtering | New behavior, must add network fixtures and real parser tests |
| Archive extraction / zip bombs / traversal / symlink attempts | Security tests needed |
| APKS/APKM/XAPK split plan correctness and ABI choice | Installation contract + device tests needed |
| Resumable downloads and changed ETag/Content-Range | Failure and recovery tests needed |
| Signing chain / attestation / certificate checks | Host and Android qualification needed |
| Installer approval after navigation/backgrounding | Widget and Android runtime tests needed |
| Accessibility, text scaling and TV D-pad | UI and device tests needed |

## Existing test inventory (not a permanent allowlist)

- `test/_paren_hash_check_test.dart`
- `test/about_headline_fit_test.dart`
- `test/app_bottom_sheet_test.dart`
- `test/app_details_container_test.dart`
- `test/app_details_paint_test.dart`
- `test/app_dropdown_field_test.dart`
- `test/app_listing_key_test.dart`
- `test/app_loading_recovery_test.dart`
- `test/app_page_version_actions_test.dart`
- `test/app_toast_host_placement_test.dart`
- `test/app_ui_scaling_test.dart`
- `test/app_visibility_filter_test.dart`
- `test/apps_scroll_work_test.dart`
- `test/bg_check_scheduling_test.dart`
- `test/bulk_category_editor_test.dart`
- `test/bulk_import_service_test.dart`
- `test/category_filter_test.dart`
- `test/custom_app_bar_test.dart`
- `test/diagnostic_snapshot_test.dart`
- `test/explained_when_off_test.dart`
- `test/export_obtainium_compat_test.dart`
- `test/flutter_test_config.dart`
- `test/forgejo_source_test.dart`
- `test/generated_form_modal_test.dart`
- `test/github_comparison_request_test.dart`
- `test/gradle_app_id_test.dart`
- `test/import_export_page_test.dart`
- `test/import_from_url_list_link_test.dart`
- `test/installed_version_reconciliation_test.dart`
- `test/json_cache_export_work_test.dart`
- `test/link_import_sheet_test.dart`
- `test/locale_resolution_test.dart`
- `test/malware_scan_warning_dialog_test.dart`
- `test/multi_source_app_actions_test.dart`
- `test/needs_attention_group_test.dart`
- `test/obtainium_import_link_test.dart`
- `test/obtainx_user_agent_test.dart`
- `test/overall_optimization_test.dart`
- `test/performance_recorder_test.dart`
- `test/performance_work_test.dart`
- `test/pick_file_test.dart`
- `test/reduced_effects_icon_colors_test.dart`
- `test/settings_provider_theme_accent_test.dart`
- `test/settle_store_lookups_test.dart`
- `test/shared_url_receiver_test.dart`
- `test/source_answered_without_update_test.dart`
- `test/source_badge_host_test.dart`
- `test/source_provider_test.dart`
- `test/store_icon_resolver_test.dart`
- `test/store_source_icons_test.dart`
- `test/switch_feedback_test.dart`
- `test/tracked_source_swap_test.dart`
- `test/unknown_version_order_test.dart`
- `test/unreconciled_version_test.dart`
- `test/update_interval_test.dart`
- `test/update_status_grouping_test.dart`
- `test/upstream_sync_regression_test.dart`
- `test/uptodown_source_test.dart`
- `test/url_import_plan_test.dart`
- `test/url_list_import_test.dart`
- `test/verification_block_attention_test.dart`
- `test/version_code_comparison_test.dart`
- `test/version_engine_test.dart`
- `test/version_hash_metadata_test.dart`
- `test/version_order_test.dart`
- `test/version_regex_assist_sheet_layout_test.dart`
- `test/version_regression_screenshots_test.dart`
- `test/version_semantics_property_test.dart`
- `test/version_suffix_test.dart`

**Contract rule:** When implementing later phases, audit every existing test against the current source and workflows. Update or delete obsolete assertions and golden fixtures as part of the same change. Do not preserve stale contracts simply for backward compatibility.
