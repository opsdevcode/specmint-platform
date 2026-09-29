mint v0
namespace example.files
target primary {
  kind repo.github
  config {
    owner "opsdevcode"
    name "specmint"
    file_path "SECURITY.md"
    file_content "# Security\nReport issues to platform@opsdevcode.com.\n"
    file_mode "0644"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a managed SECURITY.md in the repository"
  use repo.managed_file v1alpha1
  apply primary
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}
