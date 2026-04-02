# Changelog

All notable changes to this project will be documented in this file.

## 2.0.0 - 2026-04-01

- Stabilized FastAPI startup so optional AI and 5G SDK dependencies no longer crash the app at import time.
- Unified callback processing and streaming behavior around a single `/netAppCallback` implementation.
- Wired the API through the multi-core abstraction for subscriptions, callback parsing, and core status reporting.
- Added public-release basics: sanitized environment examples, GitHub Actions CI, Docker cleanup, and testable manual integration harness separation.
- Added a new repository icon and a short agentic 5G workflow introduction for public-facing release docs.
- Verified the test suite on Python 3.11 with `103 passed, 1 skipped`.
