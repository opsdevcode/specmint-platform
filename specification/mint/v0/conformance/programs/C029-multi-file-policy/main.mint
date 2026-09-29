mint v0
namespace example.main
import example.policy as policy
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Compose policy from another compilation unit"
  use repo.branch_protection v1alpha1
  apply policy.primary
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}
