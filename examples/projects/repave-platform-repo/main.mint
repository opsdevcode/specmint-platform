mint v0
namespace example.platform
target engine {
  kind repo.github
  config {
    owner "opsdevcode"
    name "repave"
    visibility "private"
    default_branch "main"
    delete_branch_on_merge true
    pull_request_required true
    required_approving_review_count 1
    require_conversation_resolution true
    required_checks {
      quality true
      test true
    }
    secret_scanning true
    push_protection true
    dependency_alerts true
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Govern the future Repave engine repository from Mint without importing Repave"
  use repo.branch_protection v1alpha1
  capabilities repo.settings v1alpha1, repo.security v1alpha1
  apply engine
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}
