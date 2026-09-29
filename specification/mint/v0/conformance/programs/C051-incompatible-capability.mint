mint v0
namespace example.mismatch
target workload {
  kind k8s.workload
  config {
    name "guard"
    namespace "platform"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Require a capability that does not match the applied target"
  use repo.branch_protection v1alpha1
  apply workload
  require authorization
  forbid mutation
  status draft
}
