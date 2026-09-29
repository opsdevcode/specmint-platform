mint v0
namespace example.main
import example.lib as lib
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Apply a qualified target that does not exist"
  use repo.branch_protection v1alpha1
  apply lib.missing
  require authorization
  forbid mutation
  status draft
}
