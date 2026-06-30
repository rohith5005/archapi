# Security Measures

ArchAPI includes baseline safety measures.

## Implemented safeguards

- Dry-run generation by default
- Explicit apply behavior
- Overwrite protection
- Low-confidence blocking
- Strict config mode
- Ignored dependency/cache folders
- Secret scanner
- Context redactor
- Policy gate
- Relative path validation
- Architecture consistency score

## Secret scanner

Implemented in:

`archapi/security/secret_scanner.py`

It detects common sensitive patterns such as API keys, tokens, secrets, private keys, and AWS-style keys.

## Context redactor

Implemented in:

`archapi/security/context_redactor.py`

It redacts sensitive-looking values before they are displayed or passed around.

## Policy gate

Implemented in:

`archapi/security/policy_gate.py`

It blocks dangerous generated paths such as `.env`, `.git`, `.venv`, private key files, and dependency folders.

## Limitations

These are safeguards, not a full security platform.

Future production hardening should include static analysis, dependency scanning, sandboxed validation, and manual review.
