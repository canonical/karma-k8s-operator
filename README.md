# alertmanager-karma

## Description

Alertmanager UI is useful for browsing alerts and managing silences, but it's
lacking as a dashboard tool - karma aims to fill this gap.  This charm deploys
and manages Karma in a Kubernetes environment.

See [the Karma source](https://github.com/prymitive/karma) for the details on Karma itself.

## Usage

To use Karma, you need to have at least one Alertmanager instance that you wish
to view.  These need to be configured via the alertmanager-servers configuration
item.

Example deployment:

```bash
juju deploy ./alertmanager-karma.charm --resource karma-image=ghcr.io/prymitive/karma:v0.86 \
  --config alertmanager-servers='AlertmanagerDemo https://alertmanager.demo.do.prometheus.io,RobustPerception http://demo.robustperception.io:9093'
juju deploy nginx-ingress-integrator
juju relate alertmanager-karma nginx-ingress-integrator
```

## Developing

Create and activate a virtualenv with the development requirements:

```bash
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

```bash
    ./run_tests
```

If you wish to skip unit or lint tests, you can run either or both of:

```bash
tox -e lint
tox -e unit
```

## Roadmap

* Tests:
  * Check for invalid config strings
  * review coverage
* TLS support for UI
* TLS client auth
* Authentication (TLS UI is a prerequisite)
* Relation to Alertmanager
* Functional tests
