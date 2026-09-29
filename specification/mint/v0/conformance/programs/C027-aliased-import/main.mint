mint v0
namespace example.main
import example.lib as lib
target primary {
  kind repo.github
  config {
    owner lib.org
    name "specmint"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Use an aliased import for repository identity"
  use repo.branch_protection v1alpha1
  apply primary
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}
