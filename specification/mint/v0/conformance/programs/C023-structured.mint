mint v0
namespace example.types
type RepoId {
  owner string
  name string
}
const spec {
  owner "opsdevcode"
  name "specmint"
}

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a sandbox marker exists after an authorized plan"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}
