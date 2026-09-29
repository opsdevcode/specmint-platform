mint v0
namespace example.k8s
target workload {
  kind k8s.workload
  config {
    name "compiler"
    namespace "specmint"
  }
}
automation as-k8s-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Require pod security on the compiler workload"
  use k8s.workload.pod_security v1alpha1
  apply workload
  evidence pod.security
  require authorization
  forbid mutation
  status draft
}
