mint v0
namespace example.main
import example.a
import example.b
target primary {
  kind repo.github
  config {
    owner Limit
    name "specmint"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Ambiguous imported constant"
  use repo.branch_protection v1alpha1
  apply primary
  require authorization
  forbid mutation
  status draft
}
