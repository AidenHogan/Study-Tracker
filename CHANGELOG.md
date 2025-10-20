# Changelog - Bug Fixes and QoL Improvements

## Known Errors Fixed

### 1. ✅ Sync Window Too Small
- **Issue**: The Garmin sync time frame selection dialog was too small (350x200)
- **Fix**: Increased dialog size to 450x250 for better readability
- **File**: `main_app.py` - `sync_and_import_garmin_data()` method

### 2. ✅ CCF/Event Study Controls Don't Auto-Refresh
- **Issue**: Changing lag, threshold, or window values in Event Study and CCF analyses didn't automatically update the charts
- **Fix**: Added event bindings to Entry widgets to trigger `update_charts()` on Enter key press and focus out
- **File**: `ui/analytics_tab.py` - `_build_exploratory_controls()` method
- **Events Added**: `<Return>` and `<FocusOut>` bindings on threshold, window, and lag entry fields

### 3. ✅ Analytics Window Layout Issues (Multiple Fixes)
- **Issue 1**: Analytics charts were compressed/squished until switching to a different page
- **Fix 1**: Modified `update_charts()` to check if charts_frame is properly sized before rendering. If not sized yet, it reschedules itself after 100ms. Added `update_idletasks()` call to force layout recalculation.
- **Issue 2**: Exploratory analyses (CCF, Event Study, Quantile) displayed large gray empty areas in bottom row
- **Fix 2**: Added `grid_remove()` calls to hide bottom chart frames when displaying single-row exploratory analyses, allowing the top row to use the full vertical space
- **Issue 3**: Charts area didn't fill the window vertically, leaving large empty space below
- **Fix 3**: Added `grid_columnconfigure(0, weight=1)` and `grid_rowconfigure(0, weight=1)` to each individual chart frame so they properly expand to fill allocated space
- **Issue 4**: Switching from exploratory analysis back to "Overview" model results left bottom frames hidden
- **Fix 4**: Added explicit `grid()` calls on bottom frames at the start of model selection path to ensure they're always visible for 4-quadrant layouts
- **File**: `ui/analytics_tab.py` - `__init__()`, `_create_widgets()`, `update_charts()`, and `_render_modeling_page()` methods
- **Implementation**: 
  - Added `_first_update_done` flag to track first render
  - Checks `charts_frame.winfo_width() > 100` for reliable sizing verification
  - Calls `update_idletasks()` to force layout updates
  - Hides unused frames for exploratory analyses
  - Explicitly re-grids frames when switching back to model results
  - Proper grid weight configuration cascading through all chart frame levels

## Quality of Life Improvements

### 4. ✅ Edit Existing Custom Factors
- **Feature**: Added ability to edit factor names and start dates
- **Implementation**:
  - Added "Edit" button next to each factor in the factor list
  - Created `edit_factor()` method that opens a dialog for editing
  - Added `update_custom_factor()` and `get_custom_factor_details()` database methods
  - Properly handles renaming (updates all log entries) and start date changes
- **Files**: 
  - `ui/custom_factors_manager.py` - UI and edit dialog
  - `core/database_manager.py` - Database operations

### 5. ✅ Help Buttons on All Tabs
- **Feature**: Added "?" help buttons to all main tabs with comprehensive explanations
- **Implementation**:
  - **Tracker Tab**: Explains timer, struggle timer, manual entry, stats, and calendar
  - **Pomodoro Tab**: Describes Pomodoro technique, settings, controls, and workflow
  - **Analytics Tab**: Already had help button - describes all models and exploratory analyses
  - **Health Tab**: Explains data sources, charts, custom factors, and tips
- **Files**:
  - `ui/tracker_tab.py` - Added `_show_help_modal()` method
  - `ui/pomodoro_tab.py` - Added `_show_help_modal()` method
  - `ui/health_tab.py` - Added `_show_help_modal()` method and messagebox import
  - `ui/analytics_tab.py` - Help already existed

### 6. ✅ Improved Garmin Authentication Error Handling
- **Feature**: Better handling of authentication failures with credential update prompts
- **Implementation**:
  - Enhanced `download_health_stats()` with retry logic and clear error messages
  - Detects authentication failures specifically (vs. network or other errors)
  - Added "Update Garmin Credentials" menu option in Garmin menu
  - Created `update_garmin_credentials()` dialog for updating email/password
  - Automatic prompt when sync fails due to invalid credentials
  - Tests credentials immediately after update and saves to garth session
- **Files**:
  - `core/garmin_downloader.py` - Enhanced error handling with retry logic
  - `main_app.py` - Added credential update dialog and menu option

## Technical Details

### Database Changes
- New function: `update_custom_factor(old_name, new_name, new_start_date)` - Updates factor details and cascades name changes to logs
- New function: `get_custom_factor_details(name)` - Retrieves factor name and start date

### UI Improvements
- All help modals use consistent formatting and comprehensive explanations
- Help buttons positioned consistently (top-right of section headers)
- Credential update dialog provides immediate feedback on authentication status

### Error Handling
- Garmin authentication attempts up to 2 times before prompting for credential update
- Distinguishes between authentication errors and network/other errors
- Clear, actionable error messages guide users to solutions

## Testing Recommendations

1. Test factor editing:
   - Edit factor name and verify calendar updates
   - Edit start date and verify log entries remain intact
   - Try renaming to an existing factor name (should show error)

2. Test help buttons:
   - Click "?" button on each tab
   - Verify all help text is readable and accurate

3. Test Garmin sync error handling:
   - Try syncing with invalid credentials
   - Verify credential update prompt appears
   - Update credentials and verify successful authentication

4. Test analytics refresh:
   - Change CCF max lag value and verify auto-refresh
   - Change Event Study threshold/window and verify auto-refresh
   - Verify analytics displays correctly on first load

## Notes
- Environment variables GARMIN_EMAIL and GARMIN_PASSWORD are now more robustly handled
- Credentials can be updated at runtime without restarting the application
- All known errors from known_errors.txt have been addressed (except the data limitation note)
