# Contributing to karma-operator
The intended use case of this operator is to be deployed together with
alertmanager-operator or karma-alertmanager-proxy-operator.

## Bugs and pull requests
- Generally, before developing enhancements to this charm, you should consider
  opening an issue explaining your use case.
- If you would like to chat with us about your use-cases or proposed
  implementation, you can reach us at
  [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/charm-dev)
  or [Discourse](https://discourse.charmhub.io/).
- It is strongly recommended that prior to engaging in any enhancements
  to this charm you familiarise your self with Juju.
- Familiarising yourself with the
  [Charmed Operator Framework](https://juju.is/docs/sdk).
  library will help you a lot when working on PRs.
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
      --resource karma-image=ghcr.io/prymitive/karma:v0.87
```

## Code overview
TODO

## Design choices
TODO

## Roadmap
* Tests:
  * Add relation to the tests
  * review coverage
  * Add karma.py to tests
* TLS support for UI -> ideally certificates via relation to easyrsa or similar
* TLS client auth
* Authentication (TLS UI is a prerequisite)
* Functional tests
