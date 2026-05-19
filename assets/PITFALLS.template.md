# Engineering Pitfalls Report

These issues were found in {{REPOS_COUNT}} real-world projects.
Our scaffold is designed to avoid them.

## Pitfall 1: {{PITFALL_NAME}}
**Seen in**: {{ISSUE_LINK}}
**Frequency**: Found in {{FREQUENCY}} of {{TOTAL}} analyzed repos
**Root cause**: {{ROOT_CAUSE}}
**Our mitigation**: {{MITIGATION}}

## Pitfall 2: {{PITFALL_NAME}}
**Seen in**: {{ISSUE_LINK}}
**Frequency**: Found in {{FREQUENCY}} of {{TOTAL}} analyzed repos
**Root cause**: {{ROOT_CAUSE}}
**Our mitigation**: {{MITIGATION}}

## Pitfall 3: {{PITFALL_NAME}}
**Seen in**: {{ISSUE_LINK}}
**Frequency**: Found in {{FREQUENCY}} of {{TOTAL}} analyzed repos
**Root cause**: {{ROOT_CAUSE}}
**Our mitigation**: {{MITIGATION}}
mitigation_file_path: {{MITIGATION_FILE_PATH}}

<!-- OPTIONAL: Add a platform_risks: block when the project targets Windows or macOS
     and platform-specific risks were identified. Each risk must have either
     mitigation_path (a file in the scaffold tree) or acknowledged: true.

platform_risks:
  - name: Windows console encoding (cp1252 vs utf-8)
    platform: windows
    mitigation_path: src/{name}/utils/security.py
  - name: Path separator differences (backslash vs forward-slash)
    platform: windows
    acknowledged: true
  - name: macOS case-insensitive filesystem collisions
    platform: macos
    acknowledged: true
-->
