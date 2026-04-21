# Production Examples

This directory holds the curated, end-user-facing example packages for
`wellplot`.

These examples are intentionally different from the development-oriented YAML
files in the repository root. A production example should:

- demonstrate a realistic packet or workflow
- stay inside the supported feature set
- use public or repository-provided demonstration data
- document the source files, supported scope, and adaptation path
- include remarks/disclaimer language that avoids reproducing proprietary
  vendor-only content as if it were an original deliverable

## Available packages

- `cbl_log_example/`
  - production example #1
  - DLIS-backed CBL/VDL packet reconstruction with heading, remarks, main and
    repeat sections, VDL rendering, and a tail page
- `forge16b_porosity_example/`
  - production example #2
  - LAS-backed open-hole packet that retains the report template while swapping
    in the replacement 30/23a-3 well data and header metadata

Start with the package README inside the example you want to adapt. Those
READMEs describe the intended scope, source data, and the files that matter
first.
