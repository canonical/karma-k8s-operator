## Integrating karma-operator
karma-operator integrates with any charm that supports the `karma_dashboard`
interface.

### Related charms
#### Alertmanager
Karma is designed to manager [alertmanager][Alertmanager operator] clusters.
Alertmanager clusters that are related to karma are automatically grouped by
cluster name. For more details see
[alertmanager documentation][Alertmanager docs].

#### Karma alertmanager proxy
The [karma alertmanager proxy][Karma alertmanager proxy operator]
is intended for remote alertmanager deployments.
For more details see
[karma-alertmanager-proxy documentation][Karma alertmanager proxy docs

#### nginx-ingress-integrator
If the karma dashboard needs to be accessed from outside the juju model, an
ingress would be needed. The easiest way to achieve this is to deploy the
[ingress integrator][Ingress operator] and relate to karma:

```shell
juju deploy nginx-ingress-integrator
juju relate karma-k8s nginx-ingress-integrator
```

[Ingress operator]: https://charmhub.io/nginx-ingress-integrator
[Alertmanager operator]: https://charmhub.io/alertmanager-k8s
[Karma alertmanager proxy operator]: https://charmhub.io/karma-alertmanager-proxy-k8s
[gh:Karma alertmanager proxy operator]: https://github.com/canonical/karma-alertmanager-proxy-operator
[gh:Karma alertmanager proxy docs]: https://github.com/canonical/karma-alertmanager-proxy-operator/blob/main/INTEGRATING.md
[Alertmanager docs]: https://github.com/canonical/alertmanager-operator/blob/main/INTEGRATING.md
