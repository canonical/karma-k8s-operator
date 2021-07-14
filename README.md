# Karma Operator (k8s)

## Description

Alertmanager UI is useful for browsing alerts and managing silences, but it's
lacking as a dashboard tool - karma aims to fill this gap. This charm deploys
and manages Karma in a Kubernetes environment.

See [the Karma source](https://github.com/prymitive/karma) for the details on Karma itself.

## Usage

To use Karma, you need to have at least one Alertmanager instance that you wish
to view. These need to be either related to Karma using the 'karma' relation,
or you can use the alertmanager-karma-proxy charm configured to point to a
remote Alertmanager instance, and relate that to alertmanager-karma.

You also need to have a working Kubernetes environment, and have bootstrapped a
Juju controller of version 2.9+, with a model ready to use with the Kubernetes
cloud.

Example deployment:

```shell
juju deploy karma-k8s
```

Then you could relate to [alertmanager](https://github.com/canonical/alertmanager-operator):
```shell
juju deploy alertmanager-k8s
juju relate alertmanager-k8s karma-k8s
```

or to a remote alertmanager via an [alertmanager proxy](https://github.com/canonical/karma-alertmanager-proxy-operator):

```shell
juju deploy karma-alertmanager-proxy-k8s
juju relate karma-alertmanager-proxy-k8s karma-k8s
```

You could add an ingress for the karma web interface:

```shell
# ingress for karma web interface
juju deploy nginx-ingress-integrator
juju relate karma-k8s nginx-ingress-integrator
```

### Configuration
- `external_hostname` (optional) - the external hostname this application should be available on.
  Set up with: `juju config external_hostname=...`

### Actions
None.

### Scale Out Usage
You may add additional Alertmanager units for high availability

```shell
juju add-unit karma-k8s
```

### Dashboard
To access Karma, use a web browser pointing to `http://service-address:8080`.


## Relations
Currently, supported relations are:
- karma-dashboard, via which karma-operator receives information about 
  alertmanager units, e.g. from alertmanager-operator or karma-alertmanager-proxy-operator.
- ingress, for interfacing with nginx-ingress-integrator.

## OCI Images
This charm can be used with the following image:
- `ghcr.io/prymitive/karma:v0.86`






