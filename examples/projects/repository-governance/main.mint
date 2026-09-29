mint v0
namespace example.repo
target primary {
  kind repo.github
  config {
    owner "opsdevcode"
    name "specmint"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Require branch protection on the primary repository"
  use repo.branch_protection v1alpha1
  apply primary
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}
