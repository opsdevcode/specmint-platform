mint v0
namespace example.badcap
target primary {
  kind repo.github
  config {
    owner "opsdevcode"
    name "specmint"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Require a capability that is only partially supported"
  use aws.account.audit v1alpha1
  apply primary
  require authorization
  forbid mutation
  status draft
}
