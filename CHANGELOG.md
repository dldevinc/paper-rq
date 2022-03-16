# Change Log

## [0.5.2](https://github.com/dldevinc/paper-rq/tree/v0.5.2) - 2022-03-16
### Bug Fixes
- Fixed job search.

## [0.5.1](https://github.com/dldevinc/paper-rq/tree/v0.5.1) - 2022-03-15
### Features
- Add `Stop job` button to the Job changeform.
### Bug Fixes
- Fixed canceling scheduled jobs.

## [0.5.0](https://github.com/dldevinc/paper-rq/tree/v0.5.0) - 2022-03-14
### ⚠ BREAKING CHANGES
- Drop support for Django 2.1.
### Features
- Add ability to stop a job execution.
- Add support for `stopped` and `cancelled` jobs.
### Bug Fixes
- Fixed a bug that did not allow filtering jobs by status value.
- Fixed issue with deleting a stopped jobs.

## [0.4.0](https://github.com/dldevinc/paper-rq/tree/v0.4.0) - 2022-01-13
### ⚠ BREAKING CHANGES
- Add support for Python 3.10 and Django 4.0.
### Features
- Add `scheduled_on` field for scheduled jobs.

## [0.3.3](https://github.com/dldevinc/paper-rq/tree/v0.3.3) - 2021-12-09
### Bug Fixes
- Fixed issue with queue name other than `default`. 

## [0.3.2](https://github.com/dldevinc/paper-rq/tree/v0.3.2) - 2021-10-14
### Features
- Add support for `rq-scheduler`.

## [0.3.1](https://github.com/dldevinc/paper-rq/tree/v0.3.1) - 2021-10-13
### Features
- Improve display of `callable` field in admin UI for class methods.
- Added `timeout` field in admin UI.

## [0.3.0](https://github.com/dldevinc/paper-rq/tree/v0.3.0) - 2021-08-19
### ⚠ BREAKING CHANGES
- Requires `paper-admin` >= 3.0 

## [0.2.0](https://github.com/dldevinc/paper-rq/tree/v0.2.0) - 2021-04-13
### Features
- Add an ability to search jobs by `ID`, `callable` string, `result` 
  and `exception`.
### Bug Fixes
- Fix multiple column ordering.

## [0.1.0](https://github.com/dldevinc/paper-rq/tree/v0.1.0) - 2021-04-12
- First release
