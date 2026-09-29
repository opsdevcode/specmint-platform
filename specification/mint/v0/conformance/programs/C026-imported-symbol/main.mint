mint v0
namespace example.main
import example.lib
target primary {
  kind repo.github
  config {
    owner org
    name "specmint"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Use an imported constant for repository identity"
  use repo.branch_protection v1alpha1
  apply primary
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}
