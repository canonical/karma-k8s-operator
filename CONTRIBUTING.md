# Contributing to karma-operator

![GitHub License](https://img.shields.io/github/license/canonical/karma-k8s-operator)
![GitHub Commit Activity](https://img.shields.io/github/commit-activity/y/canonical/karma-k8s-operator)
![GitHub Lines of Code](https://img.shields.io/tokei/lines/github/canonical/karma-k8s-operator)
![GitHub Issues](https://img.shields.io/github/issues/canonical/karma-k8s-operator)
![GitHub PRs](https://img.shields.io/github/issues-pr/canonical/karma-k8s-operator)
![GitHub Contributors](https://img.shields.io/github/contributors/canonical/karma-k8s-operator)
![GitHub Watchers](https://img.shields.io/github/watchers/canonical/karma-k8s-operator?style=social)

The intended use case of this operator is to be deployed together with
alertmanager-operator or karma-alertmanager-proxy-operator.

## Bugs and pull requests
- Generally, before developing enhancements to this charm, you should consider
  opening an issue explaining your use case.
- If you would like to chat with us about your use-cases or proposed
  implementation, you can reach us at
  [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/charm-dev)
  or [Discourse](https://discourse.charmhub.io/).
- All enhancements require review before being merged. Besides the
  code quality and test coverage, the review will also take into
  account the resulting user experience for Juju administrators using
  this charm.


## Setup

A typical setup using [snaps](https://snapcraft.io/) can be found in the
[Juju docs](https://juju.is/docs/sdk/dev-setup).

## Developing

Use your existing Python 3 development environment or create and
activate a Python 3 virtualenv

```shell
virtualenv -p python3 venv
source venv/bin/activate
```

Install the development requirements

```shell
pip install -r requirements.txt
```

Later on, upgrade packages as needed

```shell
pip install --upgrade -r requirements.txt
```

### Testing

```shell
tox -e prettify  # update your code according to linting rules
tox -e lint      # code style
tox -e static    # static analysis
tox -e unit      # unit tests
```

tox creates virtual environment for every tox environment defined in
[tox.ini](tox.ini). To activate a tox environment for manual testing,

```shell
source .tox/unit/bin/activate
```

## Build charm

Build the charm in this git repository using

```shell
charmcraft pack
```

## Usage
### Tested images
- [ghcr.io/prymitive/karma](https://ghcr.io/prymitive/karma)

### Deploy Karma

```shell
juju deploy ./karma-k8s.charm \
  --resource karma-image=ghcr.io/prymitive/karma:v0.111
```

## Code overview
- The main charm class is `KarmaCharm`, which responds to config changes
  (via `ConfigChangedEvent`) and application upgrades (via
  `UpgradeCharmEvent`).
- All lifecycle events call a common hook, `_common_exit_hook` after executing
  their own business logic. This pattern simplifies state tracking and improves
  consistency.
- On startup, the charm waits for `PebbleReadyEvent` and for an IP address to
  become available before starting the alertmanager service and declaring
  `ActiveStatus`.

## Design choices
- The charm attempts to start the karma server only if there is an active
  `alerting` relation. This is needed because if karma cannot communicate with
  an alertmanager server, it will exit immediately, which would cause pebble to
  report a failure and keep retrying.

## Roadmap
* Tests:
  * Add relation to the tests
  * review coverage
  * Add karma.py to tests
* TLS support for UI -> ideally certificates via relation to easyrsa or similar
* TLS client auth
* Authentication (TLS UI is a prerequisite)
* Functional tests
