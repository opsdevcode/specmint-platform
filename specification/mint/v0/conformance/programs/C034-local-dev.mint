mint v0
namespace example.dev
target workspace {
  kind local.dev
  config {
    workspace "specmint"
  }
}
automation as-dev-workspace-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure the local developer workspace exists"
  use local.dev.ensure_workspace v1alpha1
  apply workspace
  evidence workspace.present
  require authorization
  forbid mutation
  status draft
}
