mint v0
namespace example.multi
target repo-primary {
  kind repo.github
  config {
    owner "opsdevcode"
    name "specmint"
  }
}
target workload {
  kind k8s.workload
  config {
    name "compiler"
    namespace "specmint"
  }
}
automation as-multi-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Govern the repository and the Kubernetes workload together"
  capabilities repo.branch_protection v1alpha1, k8s.workload.pod_security v1alpha1
  apply repo-primary, workload
  evidence branch.protection, pod.security
  require authorization
  forbid mutation
  status draft
}
