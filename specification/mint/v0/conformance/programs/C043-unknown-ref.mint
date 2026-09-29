mint v0
namespace example.missing
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Apply an undeclared target"
  use repo.branch_protection v1alpha1
  apply missing-target
  require authorization
  forbid mutation
  status draft
}
