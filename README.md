# alertmanager-karma

## Description

Alertmanager UI is useful for browsing alerts and managing silences, but it's
lacking as a dashboard tool - karma aims to fill this gap.  This charm deploys
and manages Karma in a Kubernetes environment.

See [the Karma source](https://github.com/prymitive/karma) for the details on Karma itself.

## Usage

To use Karma, you need to have at least one Alertmanager instance that you wish
to view.  These need to be either related to Karma using the 'karma' relation,
or you can use the alertmanager-karma-proxy charm configured to point to a
remote Alertmanager instance, and relate that to alertmanager-karma.

You also need to have a working Kubernetes environment, and have bootstrapped a
Juju controller of version 2.9+, with a model ready to use with the Kubernetes
cloud.

Example deployment:

```bash
juju deploy alertmanager-karma --resource karma-image=ghcr.io/prymitive/karma:v0.86
juju deploy alertmanager-karma-proxy --resource placeholder-image=alpine
juju deploy nginx-ingress-integrator
juju relate alertmanager-karma:ingress nginx-ingress-integrator:ingress
juju relate alertmanager-karma-proxy:karmamanagement alertmanager-karma:karmamanagement
```

To access Karma, use a web browser pointing to http://service-address:8080.

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
  * Add relation to the tests
  * review coverage
  * Add karma.py to tests
* TLS support for UI -> ideally certificates via relation to easyrsa or similar
* TLS client auth
* Authentication (TLS UI is a prerequisite)
* Functional tests
