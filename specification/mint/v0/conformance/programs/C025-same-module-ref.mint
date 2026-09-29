mint v0
namespace example.local
const marker_name "marker.present"
automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a sandbox marker exists after an authorized plan"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker_name
  require authorization
  forbid mutation
  status draft
}
