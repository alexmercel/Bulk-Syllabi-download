# Bulk Syllabi Download

An automated script to bulk download course syllabi across multiple semesters and subcategories from the Course Completion portal.

## How to Use

1. **Install Dependencies**: 
   ```bash
   pip install selenium webdriver-manager
   ```
2. **Setup Credentials**: Define your login credentials in `config.py`.
3. **Run the Script**:
   ```bash
   python Syllabus_download.py
   ```
4. Downloaded PDF syllabi will be saved to the `downloads/<Semester>/<Subcategory>/` directory structure within the project folder.

## Passing Credentials

Create a `config.py` file with the expected variable names. Note that because this project involves syllabi, the variables utilize distinct naming:

```python
SYLLABUS_USERNAME = "your_username"
SYLLABUS_PASSWORD = "your_password"

FORM_USERNAME = "optional_other_username"
FORM_PASSWORD = "optional_other_password"
```

## Logging

Logging is handled by a custom `Logger` wrapper that reassigns `sys.stdout` and `sys.stderr`.
- Every `print()` executed by the script is echoed to the terminal and permanently appended to a local `run.log` file.
- This creates a centralized log without needing to change standard print syntax in the code base.

## Error Handling

- **Session and State Checks**: The script includes a helper function to ensure it remains logged in and correctly placed on the portal tool page before pulling rows.
- **Download Retries**: Individual syllabus downloads are wrapped in a **3-attempt retry loop** to mitigate network drops.
- **Failure Tracking & Reporting**: Any syllabus that triggers an exception, times out due to AWS errors, or cannot be successfully located via the DOM is cataloged. At the end of the script's execution run, it generates a `missing_syllabi_report.md` file listing exactly which courses were missed and why.
- **DOM Recovery**: The script contains fallback mechanisms to handle stale elements and unexpected page navigations (such as encountering S3/AWS error pages instead of files), seamlessly going back and rescanning the table.
