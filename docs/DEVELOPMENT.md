# Development Notes

Use this document for contributor-facing maintenance guidance that does not need to live in the root README.

## LOC snapshot

The root README keeps the live LOC snapshot block so it can be updated by the existing helper script.

Refresh command:

```bash
python tools/update_loc_snapshot.py
```

## Track lines of code

Recommended with `cloc`:

```bash
cloc --exclude-dir=.git,.venv,.vcpkg,build .
```

Per-language quick checks:

```bash
rg --files Languages/Python -g "*.py" | xargs wc -l
rg --files Languages/C++ -g "*.cpp" -g "*.h" | xargs wc -l
```

Windows PowerShell fallback:

```powershell
$py = Get-ChildItem Languages/Python -Recurse -File -Include *.py | Get-Content | Where-Object { $_.Trim() -ne "" } | Measure-Object
$cpp = Get-ChildItem Languages/C++ -Recurse -File -Include *.cpp,*.h | Get-Content | Where-Object { $_.Trim() -ne "" } | Measure-Object
"Python non-empty lines: $($py.Count)"
"C++ non-empty lines: $($cpp.Count)"
```

## Python comment and docstring style

- Add module docstrings to important entry files
- Use function docstrings for behavior, side effects, and environment expectations
- Prefer intent comments over obvious line-by-line comments

Template:

```python
def some_function(arg: str) -> bool:
    """
    Purpose: What this function is responsible for.
    Inputs: Explain accepted values and defaults.
    Returns: Explain success/failure semantics.
    Side effects: Files/network/UI/environment updates.
    """
```

## C++ comment style

- Add high-level comments before bootstrap or platform-specific logic
- Document Qt state-sharing points between tabs, timers, and runtime loops
- Use concise Doxygen-style comments for public header APIs

Template:

```cpp
/// Applies runtime lock state to dashboard controls while bot loop is active.
/// Keeps UI settings immutable during live execution to avoid inconsistent state.
void setDashboardRuntimeControlsEnabled(bool enabled);
```

## README maintenance rule

When adding a major feature in Python or C++, also add:

- a short behavior summary
- where it lives
- how to validate it quickly
