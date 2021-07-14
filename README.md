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
juju deploy alertmanager-karma --resource karma-image=ghcr.io/prymitive/karma:v0.86
juju deploy alertmanager-karma-proxy --resource placeholder-image=alpine
juju relate alertmanager-karma-proxy alertmanager-karma

# ingress for karma web interface
juju deploy nginx-ingress-integrator
juju relate alertmanager-karma nginx-ingress-integrator
```


### Configuration
- `external_hostname` (optional) - the external hostname this application should be available on.
  Set up with: `juju config external_hostname=...`

### Actions
None.

### Scale Out Usage
You may add additional Alertmanager units for high availability

```shell
juju add-unit alertmanager-karma
```

### Dashboard
To access Karma, use a web browser pointing to `http://service-address:8080`.


## Relations
Currently, supported relations are:
- karmamanagement, via which alertmanager-karma receives information about 
  alertmanager units, typically from alertmanager-karma-proxy.
- ingress, for interfacing with nginx-ingress-integrator.

## OCI Images
This charm can be used with the following image:
- `ghcr.io/prymitive/karma:v0.86`






