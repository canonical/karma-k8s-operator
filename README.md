# Karma Operator (k8s)

## Description

Alertmanager UI is useful for browsing alerts and managing silences, but it's
lacking as a dashboard tool - karma aims to fill this gap. This charm deploys
and manages Karma in a Kubernetes environment.

See the [Karma source][Karma source] for the details on Karma itself.

## Usage

To use Karma, you need to have at least one Alertmanager instance that you wish
to view. These need to be either related to Karma, or you can use the
[karma-alertmanager-proxy][Karma alertmanager proxy operator] charm configured
to point to a remote Alertmanager instance, and relate that to karma. For more
information see [INTEGRATING](INTEGRATING.md).

You also need to have a working Kubernetes environment, and have bootstrapped a
Juju controller of version 2.9+, with a model ready to use with the Kubernetes
cloud.

Example deployment:

```shell
juju deploy karma-k8s
```

Then you could relate to [alertmanager][Alertmanager operator]:
```shell
juju deploy alertmanager-k8s
juju relate alertmanager-k8s karma-k8s
```

or to a remote alertmanager via an
[alertmanager proxy][Karma alertmanager proxy operator]:

```shell
juju deploy karma-alertmanager-proxy-k8s --config url="http://somewhere:9093"
juju relate karma-alertmanager-proxy-k8s karma-k8s
```

You could add an [ingress][Ingress operator] for the karma web interface (see
[INTEGRATING](INTEGRATING.md) for more information):

```shell
# ingress for karma web interface
juju deploy nginx-ingress-integrator
juju relate karma-k8s nginx-ingress-integrator
```

### Scale Out Usage
Karma is an alertmanager client and therefore is not designed to operate as an
HA cluster internally. For this reason there is no difference in availability
between deploying multiple karma apps vs multiple karma units, although the
latter would be easier to configure.

To add additional Karma units for high availability,

```shell
juju add-unit karma-k8s
```

### Dashboard
To access Karma, use a web browser pointing to `http://service-address:8080`.


## Relations
Currently, supported relations are:
- `dashboard`, via which karma-operator receives information about alertmanager
  units, e.g. from [alertmanager-operator][Alertmanager operator] or
  [karma-alertmanager-proxy-operator][Karma alertmanager proxy operator].
- `ingress`, for interfacing with [nginx-ingress-integrator][Ingress operator].

## OCI Images
This charm can be used with the following image:
- `ghcr.io/prymitive/karma:v0.90`


[Karma source]: https://github.com/prymitive/karma
[Alertmanager operator]: https://charmhub.io/alertmanager-k8s
[Karma alertmanager proxy operator]: https://charmhub.io/karma-alertmanager-proxy-k8s
[gh:Alertmanager operator]: https://github.com/canonical/alertmanager-operator
[gh:Karma alertmanager proxy operator]: https://github.com/canonical/karma-alertmanager-proxy-operator
[Ingress operator]: https://charmhub.io/nginx-ingress-integrator
