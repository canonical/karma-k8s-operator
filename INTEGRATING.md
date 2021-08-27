## Integrating karma-operator
karma-operator integrates with any charm that supports the `karma_dashboard`
interface.

### Related charms
#### Alertmanager
Karma is designed to manager alertmanager clusters. Alertmanager clusters that
are related to karma are automatically grouped by cluster name.
For more details see
[alertmanager documentation](https://github.com/canonical/alertmanager-operator/blob/main/INTEGRATING.md).

#### Karma alertmanager proxy
The [karma alertmanager proxy](https://github.com/canonical/karma-alertmanager-proxy-operator/)
is intended for remote alertmanager deployments.
For more details see
[karma-alertmanager-proxy documentation](https://github.com/canonical/karma-alertmanager-proxy-operator/blob/main/INTEGRATING.md)
