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
  intent "Type mismatch from imported const"
  use repo.branch_protection v1alpha1
  apply primary
  require authorization
  forbid mutation
  status draft
}
